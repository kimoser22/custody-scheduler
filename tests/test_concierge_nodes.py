from datetime import date, datetime, timedelta, timezone

from core.models import OverrideStatus, ParentRole
from concierge.nodes import (
    ConciergeDeps,
    ConciergeState,
    commit_transaction,
    draft_confirmation_sms,
    ingest_and_dedupe,
    notify_final_success,
    parse_intent,
    process_counterparty_reply,
    process_initiator_reply,
    send_proposal_to_counterparty,
)
from concierge.ports import (
    FakeIntentParser,
    FakeSenderResolver,
    FakeSmsGateway,
    InMemoryIdempotencyStore,
    OverrideConflictError,
    ParsedIntent,
    ResolvedSender,
)
from concierge.repos import SqlAuditRepository, SqlOverrideRepository
from core.models import OverrideType


NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)


def _deps(session_fixture, sms=None):
    sms = sms or FakeSmsGateway()
    return ConciergeDeps(
        sms=sms,
        parser=FakeIntentParser(
            ParsedIntent(
                override_date=date(2026, 7, 8),
                assigned_parent=ParentRole.PARENT_B,
                reason="Taking him to trains",
            )
        ),
        resolver=FakeSenderResolver(
            {
                "+15550001": ResolvedSender(
                    user_id=101,
                    family_id=1,
                    role="Parent",
                    phone="+15550001",
                    custody_label="Parent A",
                ),
                "+15550002": ResolvedSender(
                    user_id=102,
                    family_id=1,
                    role="Parent",
                    phone="+15550002",
                    custody_label="Parent B",
                ),
            }
        ),
        overrides=SqlOverrideRepository(session_fixture),
        audit=SqlAuditRepository(session_fixture),
        idempotency=InMemoryIdempotencyStore(),
        now=NOW,
        counterparty_by_family={1: (102, "+15550002", "Parent B")},
    ), sms


def test_ingest_resolves_known_sender(session_fixture) -> None:
    deps, _ = _deps(session_fixture)
    state: ConciergeState = {
        "message_sid": "SM1",
        "inbound_from": "+15550001",
        "inbound_body": "swap",
    }
    result = ingest_and_dedupe(state, deps)
    assert result["dropped"] is False
    assert result["initiator_user_id"] == 101


def test_ingest_drops_unknown_sender(session_fixture) -> None:
    deps, _ = _deps(session_fixture)
    state: ConciergeState = {
        "message_sid": "SM1",
        "inbound_from": "+1-not-a-registered-number",
        "inbound_body": "swap",
    }
    result = ingest_and_dedupe(state, deps)
    assert result["current_step"] == "dropped"
    assert result["dropped"] is True
    assert result["error"] == "unknown_sender"


def test_ingest_no_longer_dedupes_by_sid_itself(session_fixture) -> None:
    """Message-delivery dedup moved to the transport boundary
    (LangGraphConciergeRunner.handle_sms) because claiming inside this node
    can't prevent a fresh invoke() from silently starting a second
    conversation on an existing thread_id — see tests/test_concierge_runner.py
    for the dedup coverage that actually matters."""
    deps, _ = _deps(session_fixture)
    state: ConciergeState = {
        "message_sid": "SM-repeat",
        "inbound_from": "+15550001",
        "inbound_body": "swap",
    }
    first = ingest_and_dedupe(state, deps)
    second = ingest_and_dedupe(state, deps)
    assert first["dropped"] is False
    assert second["dropped"] is False


def test_parse_intent_creates_draft(session_fixture) -> None:
    deps, _ = _deps(session_fixture)
    state = ingest_and_dedupe(
        {
            "message_sid": "SM2",
            "inbound_from": "+15550001",
            "inbound_body": "swap july 8",
        },
        deps,
    )
    parsed = parse_intent(state, deps)
    assert parsed["override_id"]
    draft = deps.overrides.get(parsed["override_id"])
    assert draft is not None
    assert draft.status == OverrideStatus.DRAFT
    assert draft.is_active is False


def test_draft_confirmation_sms_body(session_fixture) -> None:
    deps, sms = _deps(session_fixture)
    state = parse_intent(
        ingest_and_dedupe(
            {
                "message_sid": "SM3",
                "inbound_from": "+15550001",
                "inbound_body": "swap",
            },
            deps,
        ),
        deps,
    )
    next_state = draft_confirmation_sms(state, deps)
    assert next_state["current_step"] == "awaiting_initiator_confirm"
    assert "Reply YES" in sms.sent[0][1]
    assert sms.sent[0][0] == "+15550001"


def test_initiator_yes_routes_to_proposal(session_fixture) -> None:
    deps, _ = _deps(session_fixture)
    state = draft_confirmation_sms(
        parse_intent(
            ingest_and_dedupe(
                {
                    "message_sid": "SM4",
                    "inbound_from": "+15550001",
                    "inbound_body": "swap",
                },
                deps,
            ),
            deps,
        ),
        deps,
    )
    state["inbound_body"] = "YES"
    next_state = process_initiator_reply(state, deps)
    assert next_state["current_step"] == "send_proposal_to_counterparty"
    override = deps.overrides.get(state["override_id"])
    assert override is not None
    assert override.status == OverrideStatus.PENDING


def test_initiator_no_rejects(session_fixture) -> None:
    deps, sms = _deps(session_fixture)
    state = draft_confirmation_sms(
        parse_intent(
            ingest_and_dedupe(
                {
                    "message_sid": "SM5",
                    "inbound_from": "+15550001",
                    "inbound_body": "swap",
                },
                deps,
            ),
            deps,
        ),
        deps,
    )
    state["inbound_body"] = "NO"
    next_state = process_initiator_reply(state, deps)
    assert next_state["current_step"] == "completed"
    override = deps.overrides.get(state["override_id"])
    assert override is not None
    assert override.status == OverrideStatus.REJECTED
    assert any("cancelled" in body.lower() for _, body in sms.sent)


def test_happy_path_commit_activates_override(session_fixture) -> None:
    deps, sms = _deps(session_fixture)
    state = send_proposal_to_counterparty(
        process_initiator_reply(
            {
                **draft_confirmation_sms(
                    parse_intent(
                        ingest_and_dedupe(
                            {
                                "message_sid": "SM6",
                                "inbound_from": "+15550001",
                                "inbound_body": "swap",
                            },
                            deps,
                        ),
                        deps,
                    ),
                    deps,
                ),
                "inbound_body": "YES",
            },
            deps,
        ),
        deps,
    )
    assert state["current_step"] == "awaiting_counterparty_consent"
    state["inbound_body"] = "ACCEPT"
    state = process_counterparty_reply(state, deps)
    assert state["current_step"] == "commit_transaction"
    state = commit_transaction(state, deps)
    state = notify_final_success(state, deps)
    override = deps.overrides.get(state["override_id"])
    assert override is not None
    assert override.status == OverrideStatus.APPROVED
    assert override.is_active is True
    assert state["current_step"] == "completed"
    assert len(sms.sent) >= 3


class _ConflictingOverrideRepository:
    """Wraps a real OverrideRepository but simulates a concurrent commit for
    the same date racing this one — activate_and_supersede raises the way
    SqlOverrideRepository does when the unique-active-per-date index rejects
    the commit."""

    def __init__(self, inner):
        self._inner = inner

    def create_draft(self, **kwargs):
        return self._inner.create_draft(**kwargs)

    def get(self, override_id):
        return self._inner.get(override_id)

    def set_status(self, *args, **kwargs):
        return self._inner.set_status(*args, **kwargs)

    def activate_and_supersede(self, *args, **kwargs):
        raise OverrideConflictError("date already taken by another swap")


def test_commit_transaction_conflict_sends_apology_instead_of_crashing(
    session_fixture,
) -> None:
    deps, sms = _deps(session_fixture)
    state = draft_confirmation_sms(
        parse_intent(
            ingest_and_dedupe(
                {
                    "message_sid": "SM-conflict",
                    "inbound_from": "+15550001",
                    "inbound_body": "swap",
                },
                deps,
            ),
            deps,
        ),
        deps,
    )
    state["counterparty_user_id"] = 102

    deps.overrides = _ConflictingOverrideRepository(deps.overrides)

    result = commit_transaction(state, deps)

    assert result["current_step"] == "completed"
    assert result["error"] == "date_conflict"
    assert sms.sent[-2][0] == state["initiator_phone"]
    assert sms.sent[-1][0] == state["counterparty_phone"]
    assert all("just taken" in body for _, body in sms.sent[-2:])


def test_process_initiator_reply_expired_draft_notifies_and_marks_expired(
    session_fixture,
) -> None:
    deps, sms = _deps(session_fixture)
    state = draft_confirmation_sms(
        parse_intent(
            ingest_and_dedupe(
                {
                    "message_sid": "SM-exp-1",
                    "inbound_from": "+15550001",
                    "inbound_body": "swap",
                },
                deps,
            ),
            deps,
        ),
        deps,
    )
    # Simulate the initiator replying after the draft's TTL has passed.
    deps.now = deps.now + timedelta(hours=25)
    state["inbound_body"] = "YES"

    result = process_initiator_reply(state, deps)

    assert result["current_step"] == "completed"
    assert result["error"] == "expired"
    override = deps.overrides.get(state["override_id"])
    assert override is not None
    assert override.status == OverrideStatus.EXPIRED
    assert any("expired" in body.lower() for _, body in sms.sent)


def test_process_counterparty_reply_expired_notifies_both_parties(
    session_fixture,
) -> None:
    deps, sms = _deps(session_fixture)
    state = send_proposal_to_counterparty(
        process_initiator_reply(
            {
                **draft_confirmation_sms(
                    parse_intent(
                        ingest_and_dedupe(
                            {
                                "message_sid": "SM-exp-2",
                                "inbound_from": "+15550001",
                                "inbound_body": "swap",
                            },
                            deps,
                        ),
                        deps,
                    ),
                    deps,
                ),
                "inbound_body": "YES",
            },
            deps,
        ),
        deps,
    )
    assert state["current_step"] == "awaiting_counterparty_consent"

    # Simulate the counterparty replying after the request's TTL has passed.
    deps.now = deps.now + timedelta(hours=25)
    state["inbound_body"] = "ACCEPT"

    result = process_counterparty_reply(state, deps)

    assert result["current_step"] == "completed"
    assert result["error"] == "expired"
    override = deps.overrides.get(state["override_id"])
    assert override is not None
    assert override.status == OverrideStatus.EXPIRED
    assert override.is_active is False
    sent_to = {to for to, _ in sms.sent}
    assert state["initiator_phone"] in sent_to
    assert state["counterparty_phone"] in sent_to
