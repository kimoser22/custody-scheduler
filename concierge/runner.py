from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

from langgraph.types import Command

from concierge.graph import build_concierge_graph
from concierge.nodes import ConciergeDeps
from concierge.phones import normalize_phone
from concierge.ports import IdempotencyStore, SenderResolver, ThreadRegistry
from concierge.sms_copy import (
    HELP_REPLY,
    OPT_IN_REPLY,
    OPT_OUT_REPLY,
    REQUEST_WITHDRAWN_SMS,
    STILL_OPTED_OUT_REPLY,
)
from core.models import OverrideStatus

_STOP_KEYWORDS = frozenset(
    {"stop", "stopall", "unsubscribe", "cancel", "end", "quit"}
)
_HELP_KEYWORDS = frozenset({"help"})
_START_KEYWORDS = frozenset({"start", "unstop"})


def classify_keyword(body: str) -> str | None:
    """Return 'stop', 'help', or 'start' when the entire body is a reserved keyword."""
    token = body.strip().lower()
    if token in _STOP_KEYWORDS:
        return "stop"
    if token in _HELP_KEYWORDS:
        return "help"
    if token in _START_KEYWORDS:
        return "start"
    return None


def _send_keyword_reply(deps: ConciergeDeps, to: str, body: str) -> None:
    """Keyword ACKs must reach opted-out phones (STOP confirmation, HELP, START)."""
    deps.sms.send_forced(to=to, body=body)


class ConciergeRunner(Protocol):
    def handle_sms(
        self, *, message_sid: str, from_phone: str, body: str
    ) -> dict[str, Any]: ...


@dataclass
class InMemoryThreadRegistry:
    """Maps a phone number to an open LangGraph thread awaiting reply.

    Process-local: used by the simulator and tests. Production uses
    SqlThreadRegistry so a paused handshake survives a restart.
    """

    by_phone: dict[str, str] = field(default_factory=dict)

    def get(self, phone: str) -> str | None:
        return self.by_phone.get(phone)

    def set(self, phone: str, thread_id: str) -> None:
        self.by_phone[phone] = thread_id

    def clear(self, phone: str) -> None:
        self.by_phone.pop(phone, None)

    def clear_by_thread(self, thread_id: str) -> None:
        for phone, mapped in list(self.by_phone.items()):
            if mapped == thread_id:
                self.by_phone.pop(phone, None)


@dataclass
class LangGraphConciergeRunner:
    deps: ConciergeDeps
    registry: ThreadRegistry = field(default_factory=InMemoryThreadRegistry)
    checkpointer: Any | None = None
    _graph: Any = field(init=False)

    def __post_init__(self) -> None:
        self._graph = build_concierge_graph(self.deps, checkpointer=self.checkpointer)

    def _withdraw_open_proposals(self, from_phone: str) -> None:
        """Reject the sender's open Draft/Pending work and tear down SMS pause."""
        sender = self.deps.resolver.resolve(from_phone)
        counterparty_phone: str | None = None
        if sender is not None:
            # Prefer parents_by_family (prod factory shape); fall back to the
            # legacy single-counterparty map used by tests/simulator.
            parents = (self.deps.parents_by_family or {}).get(sender.family_id)
            if parents:
                for user_id, phone, _label in parents:
                    if user_id != sender.user_id:
                        counterparty_phone = phone
                        break
            else:
                counterparty = self.deps.counterparty_by_family.get(sender.family_id)
                if counterparty is not None:
                    _, counterparty_phone, _ = counterparty

        thread_ids: set[str] = set()
        own_thread = self.registry.get(from_phone)
        if own_thread:
            thread_ids.add(own_thread)
        if counterparty_phone:
            cp_thread = self.registry.get(counterparty_phone)
            if cp_thread:
                thread_ids.add(cp_thread)
        for thread_id in thread_ids:
            self.registry.clear_by_thread(thread_id)
        self.registry.clear(from_phone)
        if counterparty_phone:
            self.registry.clear(counterparty_phone)

        if sender is None:
            return

        open_overrides = self.deps.overrides.list_open_by_requester(
            sender.user_id, now=self.deps.now
        )
        if not open_overrides:
            return

        for override in open_overrides:
            assert override.id is not None
            self.deps.overrides.set_status(
                override.id,
                OverrideStatus.REJECTED,
                is_active=False,
                decided_by_user_id=sender.user_id,
                decided_at=self.deps.now,
            )
            self.deps.audit.append(
                family_id=sender.family_id,
                actor_role=sender.role,
                action_type="override_withdrawn_opt_out",
                description=(
                    f"Override {override.id} withdrawn when requester opted out of SMS"
                ),
                previous_state_id=override.id,
                timestamp=self.deps.now,
            )

        if counterparty_phone:
            self.deps.sms.send(to=counterparty_phone, body=REQUEST_WITHDRAWN_SMS)

    def handle_sms(
        self, *, message_sid: str, from_phone: str, body: str
    ) -> dict[str, Any]:
        from_phone = normalize_phone(from_phone)
        # Claim delivery of this exact message_sid once, before touching the
        # registry or the graph — for both a brand-new conversation and a
        # reply. A thread_id (below) is unique per conversation and never
        # reused, so invoking the graph again for an already-claimed sid —
        # whether a concurrent duplicate delivery or a delayed Twilio retry
        # arriving after the conversation already moved on to the other
        # parent — would silently start a second, unrelated conversation on
        # top of the first rather than being recognized as a duplicate.
        # Claiming here, before any invoke(), is what prevents that.
        if not self.deps.idempotency.claim(message_sid):
            return {"status": "dropped", "reason": "duplicate_message_sid"}

        keyword = classify_keyword(body)
        if keyword == "stop":
            self._withdraw_open_proposals(from_phone)
            self.deps.opt_outs.opt_out(from_phone)
            _send_keyword_reply(self.deps, from_phone, OPT_OUT_REPLY)
            return {"status": "ok", "reason": "opt_out"}
        if keyword == "start":
            self.deps.opt_outs.opt_in(from_phone)
            _send_keyword_reply(self.deps, from_phone, OPT_IN_REPLY)
            return {"status": "ok", "reason": "opt_in"}
        if keyword == "help":
            _send_keyword_reply(self.deps, from_phone, HELP_REPLY)
            return {"status": "ok", "reason": "help"}

        if self.deps.opt_outs.is_opted_out(from_phone):
            _send_keyword_reply(self.deps, from_phone, STILL_OPTED_OUT_REPLY)
            return {"status": "ok", "reason": "opted_out"}

        open_thread = self.registry.get(from_phone)
        if open_thread:
            result = self._graph.invoke(
                Command(resume=body),
                config={"configurable": {"thread_id": open_thread}},
            )
            lang_thread_id = open_thread
        else:
            sender = self.deps.resolver.resolve(from_phone)
            if sender is None:
                return {"status": "ignored", "reason": "unknown_sender"}
            # A fresh id per conversation, never derived solely from
            # phone/family, so it can never collide with a prior or
            # concurrent conversation involving the same phone number.
            lang_thread_id = f"family:{sender.family_id}:phone:{from_phone}:{uuid4().hex[:12]}"
            result = self._graph.invoke(
                {
                    "message_sid": message_sid,
                    "inbound_from": from_phone,
                    "inbound_body": body,
                },
                config={"configurable": {"thread_id": lang_thread_id}},
            )

        if isinstance(result, dict) and result.get("dropped"):
            return {"status": "dropped", "result": result}

        interrupts = result.get("__interrupt__") if isinstance(result, dict) else None
        waiting = bool(interrupts)

        if waiting:
            # Keep LangGraph checkpoint thread id stable across resumes.
            counterparty = (
                result.get("counterparty_phone") if isinstance(result, dict) else None
            )
            step_hint = None
            if interrupts:
                first = interrupts[0]
                value = getattr(first, "value", first)
                if isinstance(value, dict):
                    step_hint = value.get("step")
            if step_hint == "awaiting_counterparty_consent" and counterparty:
                self.registry.clear(from_phone)
                self.registry.set(counterparty, lang_thread_id)
            else:
                self.registry.set(from_phone, lang_thread_id)
            return {
                "status": "waiting",
                "thread_id": lang_thread_id,
                "result": result,
            }

        if isinstance(result, dict):
            self.registry.clear(result.get("initiator_phone", ""))
            self.registry.clear(result.get("counterparty_phone", ""))
            self.registry.clear(from_phone)

        return {"status": "ok", "result": result}


@dataclass
class RecordingConciergeRunner:
    calls: list[dict[str, str]] = field(default_factory=list)
    response: dict[str, Any] = field(default_factory=lambda: {"status": "ok"})

    def handle_sms(
        self, *, message_sid: str, from_phone: str, body: str
    ) -> dict[str, Any]:
        self.calls.append(
            {"message_sid": message_sid, "from_phone": from_phone, "body": body}
        )
        return self.response
