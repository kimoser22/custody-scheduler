from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, TypedDict

from core.approvals import ApprovalError, Decision, decide_override
from core.handshake import HandshakeError, InitiatorDecision, apply_initiator_confirm
from core.models import OverrideStatus
from concierge.ports import (
    AuditRepository,
    IdempotencyStore,
    IntentParser,
    OverrideConflictError,
    OverrideRepository,
    SenderResolver,
    SmsGateway,
)


OVERRIDE_TTL = timedelta(hours=24)

UNCLEAR_REQUEST_SMS = (
    "Sorry, I couldn't understand that swap request. Please text a date and "
    "the parent, e.g. 'swap 2026-08-15 to Parent B'."
)


class ConciergeState(TypedDict, total=False):
    thread_id: str
    message_sid: str
    inbound_from: str
    inbound_body: str
    family_id: int
    initiator_user_id: int
    initiator_role: str
    initiator_phone: str
    initiator_label: str
    counterparty_phone: str
    counterparty_user_id: int
    counterparty_label: str
    override_id: int
    parsed_intent: dict[str, Any]
    current_step: str
    dropped: bool
    error: str


@dataclass
class ConciergeDeps:
    sms: SmsGateway
    parser: IntentParser
    resolver: SenderResolver
    overrides: OverrideRepository
    audit: AuditRepository
    idempotency: IdempotencyStore
    now: datetime
    counterparty_by_family: dict[int, tuple[int, str, str]]
    parents_by_family: dict[int, list[tuple[int, str, str]]] | None = None


def ingest_and_dedupe(state: ConciergeState, deps: ConciergeDeps) -> ConciergeState:
    # Message-delivery deduplication (by message_sid) happens once, at the
    # transport boundary, before this node ever runs — see
    # concierge.runner.LangGraphConciergeRunner.handle_sms, which claims a
    # fresh, never-reused thread_id per conversation. Re-invoking this node
    # (a plain, non-resume invoke()) on an existing thread_id silently starts
    # a second, unrelated conversation on top of the first rather than being
    # "deduped" here, so claiming must happen before invoke() is ever called,
    # not inside the graph. Direct callers of the graph that bypass the
    # runner (concierge.simulator, tests) are responsible for only invoking
    # a given thread_id once with a fresh message_sid.
    sender = deps.resolver.resolve(state["inbound_from"])
    if sender is None:
        return {
            **state,
            "current_step": "dropped",
            "dropped": True,
            "error": "unknown_sender",
        }

    next_state: ConciergeState = {
        **state,
        "family_id": sender.family_id,
        "initiator_user_id": sender.user_id,
        "initiator_role": sender.role,
        "initiator_phone": sender.phone,
        "initiator_label": sender.custody_label,
        "current_step": "parse_intent",
        "dropped": False,
    }

    parents = (deps.parents_by_family or {}).get(sender.family_id)
    if parents:
        for user_id, phone, label in parents:
            if user_id != sender.user_id:
                next_state["counterparty_user_id"] = user_id
                next_state["counterparty_phone"] = phone
                next_state["counterparty_label"] = label
                break
    else:
        counterparty = deps.counterparty_by_family.get(sender.family_id)
        if counterparty:
            user_id, phone, label = counterparty
            next_state["counterparty_user_id"] = user_id
            next_state["counterparty_phone"] = phone
            next_state["counterparty_label"] = label
    return next_state


def parse_intent(state: ConciergeState, deps: ConciergeDeps) -> ConciergeState:
    intent = deps.parser.parse(state["inbound_body"])
    if intent is None:
        # Fail safe: the message didn't clearly specify a date + parent. Ask the
        # initiator to clarify instead of drafting a guessed custody handoff.
        deps.sms.send(state["initiator_phone"], UNCLEAR_REQUEST_SMS)
        deps.audit.append(
            family_id=state["family_id"],
            actor_role=state["initiator_role"],
            action_type="parse_unclear",
            description="Could not parse swap request; asked for clarification",
            previous_state_id=None,
            timestamp=deps.now,
        )
        return {**state, "current_step": "unparseable", "error": "unparseable"}

    draft = deps.overrides.create_draft(
        family_id=state["family_id"],
        override_date=intent.override_date,
        assigned_parent=intent.assigned_parent,
        override_type=intent.override_type,
        description=intent.reason,
        requested_by_user_id=state["initiator_user_id"],
        expires_at=deps.now + OVERRIDE_TTL,
    )
    assert draft.id is not None
    deps.audit.append(
        family_id=state["family_id"],
        actor_role=state["initiator_role"],
        action_type="draft_created",
        description=f"Draft override {draft.id} for {intent.override_date}",
        previous_state_id=None,
        timestamp=deps.now,
    )
    return {
        **state,
        "override_id": draft.id,
        "parsed_intent": {
            "override_date": intent.override_date.isoformat(),
            "assigned_parent": intent.assigned_parent.value,
            "reason": intent.reason,
        },
        "thread_id": f"family:{state['family_id']}:override:{draft.id}",
        "current_step": "draft_confirmation_sms",
    }


def draft_confirmation_sms(state: ConciergeState, deps: ConciergeDeps) -> ConciergeState:
    intent = state["parsed_intent"]
    body = (
        f"You want to swap {intent['override_date']} to {intent['assigned_parent']}. "
        "Reply YES to send to the other parent, or NO to cancel."
    )
    deps.sms.send(state["initiator_phone"], body)
    return {**state, "current_step": "awaiting_initiator_confirm"}


def process_initiator_reply(state: ConciergeState, deps: ConciergeDeps) -> ConciergeState:
    text = state["inbound_body"].strip().upper()
    decision = InitiatorDecision.YES if text.startswith("YES") else InitiatorDecision.NO
    override = deps.overrides.get(state["override_id"])
    assert override is not None and override.expires_at is not None
    result = apply_initiator_confirm(
        current_status=override.status,
        decision=decision,
        now=deps.now,
        expires_at=override.expires_at,
    )
    if not result.ok:
        if result.error == HandshakeError.EXPIRED:
            deps.overrides.set_status(
                state["override_id"], OverrideStatus.EXPIRED, is_active=False
            )
            deps.sms.send(state["initiator_phone"], "Sorry, that swap request has expired.")
        deps.audit.append(
            family_id=state["family_id"],
            actor_role=state["initiator_role"],
            action_type="initiator_reply_error",
            description=f"Initiator reply failed: {result.error.value if result.error else 'unknown'}",
            previous_state_id=state["override_id"],
            timestamp=deps.now,
        )
        return {
            **state,
            "error": result.error.value if result.error else "handshake_error",
            "current_step": "completed",
        }

    deps.overrides.set_status(
        state["override_id"],
        result.new_status,
        is_active=False,
    )
    deps.audit.append(
        family_id=state["family_id"],
        actor_role=state["initiator_role"],
        action_type="initiator_reply",
        description=f"Initiator said {decision.value}",
        previous_state_id=state["override_id"],
        timestamp=deps.now,
    )

    if decision == InitiatorDecision.NO:
        deps.sms.send(state["initiator_phone"], "Override request cancelled.")
        return {**state, "current_step": "completed"}

    return {**state, "current_step": "send_proposal_to_counterparty"}


def send_proposal_to_counterparty(state: ConciergeState, deps: ConciergeDeps) -> ConciergeState:
    intent = state["parsed_intent"]
    body = (
        f"{state['initiator_label']} requests a schedule swap for {intent['override_date']}. "
        f"Reason: '{intent['reason']}'. Reply ACCEPT or DENY."
    )
    deps.sms.send(state["counterparty_phone"], body)
    return {**state, "current_step": "awaiting_counterparty_consent"}


def process_counterparty_reply(state: ConciergeState, deps: ConciergeDeps) -> ConciergeState:
    text = state["inbound_body"].strip().upper()
    approve = text.startswith("ACCEPT")
    override = deps.overrides.get(state["override_id"])
    assert override is not None and override.expires_at is not None

    result = decide_override(
        current_status=override.status,
        requested_by_user_id=override.requested_by_user_id or 0,
        actor_user_id=state["counterparty_user_id"],
        decision=Decision.APPROVE if approve else Decision.REJECT,
        now=deps.now,
        expires_at=override.expires_at,
    )
    if not result.ok:
        if result.error == ApprovalError.EXPIRED:
            deps.overrides.set_status(
                state["override_id"], OverrideStatus.EXPIRED, is_active=False
            )
            error_message = "Sorry, that swap request has expired."
        else:
            error_message = "That swap request was already decided."
        deps.audit.append(
            family_id=state["family_id"],
            actor_role="Parent",
            action_type="counterparty_decision_error",
            description=f"Counterparty decision failed: {result.error.value if result.error else 'unknown'}",
            previous_state_id=state["override_id"],
            timestamp=deps.now,
        )
        deps.sms.send(state["initiator_phone"], error_message)
        deps.sms.send(state["counterparty_phone"], error_message)
        return {
            **state,
            "error": result.error.value if result.error else "decision_error",
            "current_step": "completed",
        }

    if result.new_status == OverrideStatus.REJECTED:
        deps.overrides.set_status(
            state["override_id"],
            OverrideStatus.REJECTED,
            is_active=False,
            decided_by_user_id=state["counterparty_user_id"],
            decided_at=deps.now,
        )
        deps.audit.append(
            family_id=state["family_id"],
            actor_role="Parent",
            action_type="counterparty_deny",
            description="Counterparty denied",
            previous_state_id=state["override_id"],
            timestamp=deps.now,
        )
        deps.sms.send(state["initiator_phone"], "Your swap request was denied.")
        deps.sms.send(state["counterparty_phone"], "You denied the swap request.")
        return {**state, "current_step": "completed"}

    return {**state, "current_step": "commit_transaction"}


def commit_transaction(state: ConciergeState, deps: ConciergeDeps) -> ConciergeState:
    try:
        deps.overrides.activate_and_supersede(
            state["override_id"],
            decided_by_user_id=state["counterparty_user_id"],
            decided_at=deps.now,
        )
    except OverrideConflictError:
        deps.audit.append(
            family_id=state["family_id"],
            actor_role="Parent",
            action_type="commit_conflict",
            description=f"Override {state['override_id']} lost the race for its date",
            previous_state_id=state["override_id"],
            timestamp=deps.now,
        )
        conflict_message = "Sorry, that date was just taken by another swap request."
        deps.sms.send(state["initiator_phone"], conflict_message)
        deps.sms.send(state["counterparty_phone"], conflict_message)
        return {**state, "error": "date_conflict", "current_step": "completed"}

    deps.audit.append(
        family_id=state["family_id"],
        actor_role="Parent",
        action_type="committed",
        description=f"Override {state['override_id']} activated",
        previous_state_id=state["override_id"],
        timestamp=deps.now,
    )
    return {**state, "current_step": "notify_final_success"}


def notify_final_success(state: ConciergeState, deps: ConciergeDeps) -> ConciergeState:
    intent = state["parsed_intent"]
    body = f"Confirmed: {intent['override_date']} is now with {intent['assigned_parent']}."
    deps.sms.send(state["initiator_phone"], body)
    deps.sms.send(state["counterparty_phone"], body)
    return {**state, "current_step": "completed"}
