"""Persisted SMS opt-out: STOP stores suppression; outbound sends respect it."""

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
from concierge.repos import SqlAuditRepository, SqlOptOutStore, SqlOverrideRepository
from concierge.runner import LangGraphConciergeRunner, classify_keyword
from core.models import ParentRole
from database.schema import OverrideTable, SmsOptOutTable


NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)


def _build_runner(session_fixture, *, sms=None, opt_outs=None):
    inner = sms or FakeSmsGateway()
    opt_outs = opt_outs or InMemoryOptOutStore()
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


def test_classify_keyword_recognizes_start() -> None:
    assert classify_keyword("START") == "start"
    assert classify_keyword("unstop") == "start"


def test_stop_persists_opt_out_row(session_fixture) -> None:
    opt_outs = SqlOptOutStore(session_fixture)
    runner, inner, _ = _build_runner(session_fixture, opt_outs=opt_outs)

    result = runner.handle_sms(
        message_sid="SM-stop-persist",
        from_phone="+15550001",
        body="STOP",
    )

    assert result["reason"] == "opt_out"
    assert opt_outs.is_opted_out("+15550001")
    rows = session_fixture.exec(select(SmsOptOutTable)).all()
    assert len(rows) == 1
    assert rows[0].phone == "+15550001"
    assert any("opted out" in body.lower() for _, body in inner.sent)


def test_after_stop_swap_does_not_send_further_sms(session_fixture) -> None:
    runner, inner, opt_outs = _build_runner(session_fixture)

    runner.handle_sms(
        message_sid="SM-stop-2", from_phone="+15550001", body="STOP"
    )
    sent_after_stop = len(inner.sent)
    assert opt_outs.is_opted_out("+15550001")

    result = runner.handle_sms(
        message_sid="SM-swap-blocked",
        from_phone="+15550001",
        body="swap 2026-07-08 to Parent B for trains",
    )

    assert result["status"] == "ok"
    assert result["reason"] == "opted_out"
    assert len(inner.sent) == sent_after_stop + 1  # one "you're opted out" notice
    assert not any(
        "want to swap" in body.lower() or "confirm" in body.lower()
        for _, body in inner.sent[sent_after_stop:]
    )
    assert session_fixture.exec(select(OverrideTable)).all() == []


def test_start_clears_opt_out_and_allows_sms_again(session_fixture) -> None:
    runner, inner, opt_outs = _build_runner(session_fixture)

    runner.handle_sms(
        message_sid="SM-stop-3", from_phone="+15550001", body="STOP"
    )
    assert opt_outs.is_opted_out("+15550001")

    result = runner.handle_sms(
        message_sid="SM-start-1", from_phone="+15550001", body="START"
    )
    assert result["reason"] == "opt_in"
    assert not opt_outs.is_opted_out("+15550001")
    assert any("resubscribed" in body.lower() or "opted in" in body.lower() for _, body in inner.sent)

    waiting = runner.handle_sms(
        message_sid="SM-swap-after-start",
        from_phone="+15550001",
        body="swap 2026-07-08 to Parent B for trains",
    )
    assert waiting["status"] == "waiting"
    assert any("2026-07-08" in body for _, body in inner.sent)


def test_opt_out_aware_gateway_skips_send_when_opted_out() -> None:
    inner = FakeSmsGateway()
    store = InMemoryOptOutStore()
    store.opt_out("+15550001")
    gate = OptOutAwareSmsGateway(inner, store)

    gate.send(to="+15550001", body="should not send")
    gate.send_forced(to="+15550001", body="forced ok")
    gate.send(to="+15550002", body="other ok")

    assert inner.sent == [
        ("+15550001", "forced ok"),
        ("+15550002", "other ok"),
    ]
