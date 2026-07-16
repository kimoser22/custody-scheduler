from datetime import date, datetime, timezone

from sqlmodel import select

from core.models import OverrideStatus, ParentRole
from concierge.nodes import ConciergeDeps
from concierge.ports import (
    FakeIntentParser,
    FakeSenderResolver,
    FakeSmsGateway,
    InMemoryIdempotencyStore,
    ParsedIntent,
    ResolvedSender,
)
from concierge.repos import SqlAuditRepository, SqlOverrideRepository
from concierge.runner import LangGraphConciergeRunner
from database.schema import OverrideTable


NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)


def test_runner_end_to_end_double_handshake(session_fixture) -> None:
    sms = FakeSmsGateway()
    deps = ConciergeDeps(
        sms=sms,
        parser=FakeIntentParser(
            ParsedIntent(
                override_date=date(2026, 7, 8),
                assigned_parent=ParentRole.PARENT_B,
                reason="trains",
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
    )
    runner = LangGraphConciergeRunner(deps=deps)

    first = runner.handle_sms(
        message_sid="SM-run-1",
        from_phone="+15550001",
        body="swap please",
    )
    assert first["status"] == "waiting"

    second = runner.handle_sms(
        message_sid="SM-run-2",
        from_phone="+15550001",
        body="YES",
    )
    assert second["status"] == "waiting"

    final = runner.handle_sms(
        message_sid="SM-run-3",
        from_phone="+15550002",
        body="ACCEPT",
    )
    assert final["status"] == "ok"
    override_id = final["result"]["override_id"]
    override = deps.overrides.get(override_id)
    assert override is not None
    assert override.status == OverrideStatus.APPROVED
    assert override.is_active is True


def _build_runner(session_fixture) -> tuple[LangGraphConciergeRunner, FakeSmsGateway]:
    sms = FakeSmsGateway()
    deps = ConciergeDeps(
        sms=sms,
        parser=FakeIntentParser(
            ParsedIntent(
                override_date=date(2026, 7, 8),
                assigned_parent=ParentRole.PARENT_B,
                reason="trains",
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
    )
    return LangGraphConciergeRunner(deps=deps), sms


def test_runner_resume_leg_drops_an_already_claimed_message_sid(session_fixture) -> None:
    """Regression test: previously, only the initial-message leg of handle_sms
    consulted the idempotency store (inside ingest_and_dedupe); the resume leg
    (Command(resume=...)) skipped it entirely. Twilio's at-least-once webhook
    delivery can redeliver the same reply while the thread is still open —
    e.g. two near-simultaneous deliveries of the same "YES" reaching separate
    concurrent requests. Pre-claiming the sid (as a concurrent delivery
    would) and asserting the resume leg refuses to process it proves the
    guard fires before the graph (and any SMS) is touched."""
    runner, sms = _build_runner(session_fixture)

    first = runner.handle_sms(
        message_sid="SM-retry-1", from_phone="+15550001", body="swap please"
    )
    assert first["status"] == "waiting"

    # Simulate a concurrent duplicate delivery of the reply having already
    # claimed this message_sid moments earlier.
    assert runner.deps.idempotency.claim("SM-retry-2") is True

    result = runner.handle_sms(
        message_sid="SM-retry-2", from_phone="+15550001", body="YES"
    )

    assert result == {"status": "dropped", "reason": "duplicate_message_sid"}
    # The resume never ran, so no proposal SMS went out to the counterparty.
    assert not any("requests a schedule swap" in body for _, body in sms.sent)


def test_runner_drops_duplicate_initial_message_sid(session_fixture) -> None:
    """Two brand-new conversations delivered with the same message_sid (a
    redelivered first message) must not both create a draft — dedup now
    happens once at the top of handle_sms, before any thread lookup."""
    runner, _ = _build_runner(session_fixture)

    first = runner.handle_sms(
        message_sid="SM-init-dup", from_phone="+15550001", body="swap please"
    )
    assert first["status"] == "waiting"

    retried = runner.handle_sms(
        message_sid="SM-init-dup", from_phone="+15550001", body="swap please again"
    )
    assert retried == {"status": "dropped", "reason": "duplicate_message_sid"}

    drafts = session_fixture.exec(select(OverrideTable)).all()
    assert len(drafts) == 1


def test_runner_late_retry_after_handoff_does_not_corrupt_pending_conversation(
    session_fixture,
) -> None:
    """Regression test for the deeper bug behind the idempotency fix above:
    a redelivered "YES" arriving AFTER the conversation has already handed
    off to the counterparty (so the registry no longer maps the initiator's
    phone) used to fall through to the "new conversation" branch. Because
    thread_id used to be deterministic from phone+family, invoking the graph
    fresh on that thread_id silently started a second conversation on top of
    the first, permanently orphaning the counterparty's pending interrupt.
    With per-conversation-unique thread_ids plus the top-of-handle_sms
    idempotency claim, the late retry is dropped before it can touch the
    graph at all, and the real handshake completes normally."""
    runner, sms = _build_runner(session_fixture)

    first = runner.handle_sms(
        message_sid="SM-late-1", from_phone="+15550001", body="swap please"
    )
    assert first["status"] == "waiting"

    second = runner.handle_sms(
        message_sid="SM-late-2", from_phone="+15550001", body="YES"
    )
    assert second["status"] == "waiting"  # handed off to the counterparty

    # Twilio redelivers the initiator's "YES" well after the handoff — the
    # registry no longer has an entry for +15550001.
    late_retry = runner.handle_sms(
        message_sid="SM-late-2", from_phone="+15550001", body="YES"
    )
    assert late_retry == {"status": "dropped", "reason": "duplicate_message_sid"}

    # The counterparty's real reply still resolves the original conversation.
    final = runner.handle_sms(
        message_sid="SM-late-3", from_phone="+15550002", body="ACCEPT"
    )
    assert final["status"] == "ok"
    override_id = final["result"]["override_id"]
    override = SqlOverrideRepository(session_fixture).get(override_id)
    assert override is not None
    assert override.status == OverrideStatus.APPROVED
    assert override.is_active is True

    # Exactly one draft/override was ever created — the late retry never
    # started a second, orphaned conversation.
    all_overrides = session_fixture.exec(select(OverrideTable)).all()
    assert len(all_overrides) == 1
    assert any("Confirmed" in body for _, body in sms.sent)
