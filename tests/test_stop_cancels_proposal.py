"""Initiator STOP must cancel open proposals and tear down the counterparty handshake."""

from datetime import date, datetime, timezone

from sqlmodel import select

from concierge.nodes import ConciergeDeps
from concierge.ports import (
    FakeIntentParser,
    FakeSenderResolver,
    FakeSmsGateway,
    InMemoryIdempotencyStore,
    InMemoryOptOutStore,
    OptOutAwareSmsGateway,
    ParsedIntent,
    ResolvedSender,
)
from concierge.repos import SqlAuditRepository, SqlOverrideRepository
from concierge.runner import LangGraphConciergeRunner
from core.models import OverrideStatus, ParentRole
from database.schema import OverrideTable


NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)


def _build_runner(session_fixture):
    inner = FakeSmsGateway()
    opt_outs = InMemoryOptOutStore()
    gated = OptOutAwareSmsGateway(inner, opt_outs)
    deps = ConciergeDeps(
        sms=gated,
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
        opt_outs=opt_outs,
    )
    return LangGraphConciergeRunner(deps=deps), inner, opt_outs


def test_initiator_stop_after_yes_rejects_pending_and_blocks_accept(
    session_fixture,
) -> None:
    runner, inner, opt_outs = _build_runner(session_fixture)

    assert (
        runner.handle_sms(
            message_sid="SM-stop-cancel-1",
            from_phone="+15550001",
            body="swap please",
        )["status"]
        == "waiting"
    )
    assert (
        runner.handle_sms(
            message_sid="SM-stop-cancel-2",
            from_phone="+15550001",
            body="YES",
        )["status"]
        == "waiting"
    )

    pending = session_fixture.exec(select(OverrideTable)).all()
    assert len(pending) == 1
    assert pending[0].status == OverrideStatus.PENDING.value
    assert runner.registry.get("+15550002") is not None

    result = runner.handle_sms(
        message_sid="SM-stop-cancel-3",
        from_phone="+15550001",
        body="STOP",
    )
    assert result["reason"] == "opt_out"
    assert opt_outs.is_opted_out("+15550001")

    session_fixture.refresh(pending[0])
    assert pending[0].status == OverrideStatus.REJECTED.value
    assert pending[0].is_active is False
    assert runner.registry.get("+15550001") is None
    assert runner.registry.get("+15550002") is None
    assert any(
        phone == "+15550002" and "withdrew" in body.lower()
        for phone, body in inner.sent
    )

    accept = runner.handle_sms(
        message_sid="SM-stop-cancel-4",
        from_phone="+15550002",
        body="ACCEPT",
    )
    # No open thread — ACCEPT starts a new parse, does not approve the old row.
    session_fixture.refresh(pending[0])
    assert pending[0].status == OverrideStatus.REJECTED.value
    assert pending[0].is_active is False
    assert accept["status"] != "ok" or (
        isinstance(accept.get("result"), dict)
        and accept["result"].get("override_id") != pending[0].id
    )


def test_initiator_stop_during_draft_rejects_draft(session_fixture) -> None:
    runner, inner, _ = _build_runner(session_fixture)

    assert (
        runner.handle_sms(
            message_sid="SM-stop-draft-1",
            from_phone="+15550001",
            body="swap please",
        )["status"]
        == "waiting"
    )
    draft = session_fixture.exec(select(OverrideTable)).one()
    assert draft.status == OverrideStatus.DRAFT.value

    runner.handle_sms(
        message_sid="SM-stop-draft-2",
        from_phone="+15550001",
        body="STOP",
    )

    session_fixture.refresh(draft)
    assert draft.status == OverrideStatus.REJECTED.value
    assert runner.registry.get("+15550001") is None
    assert any(
        phone == "+15550002" and "withdrew" in body.lower()
        for phone, body in inner.sent
    )
