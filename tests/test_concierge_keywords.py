"""STOP / HELP keywords must short-circuit before any swap handshake."""

from datetime import date, datetime, timezone

from sqlmodel import select

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
from concierge.runner import LangGraphConciergeRunner, classify_keyword
from core.models import ParentRole
from database.schema import OverrideTable


NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)


def _build_runner(session_fixture, sms: FakeSmsGateway | None = None):
    sms = sms or FakeSmsGateway()
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
            }
        ),
        overrides=SqlOverrideRepository(session_fixture),
        audit=SqlAuditRepository(session_fixture),
        idempotency=InMemoryIdempotencyStore(),
        now=NOW,
        counterparty_by_family={1: (102, "+15550002", "Parent B")},
    )
    return LangGraphConciergeRunner(deps=deps), sms


def test_classify_keyword_recognizes_stop_and_help() -> None:
    assert classify_keyword("STOP") == "stop"
    assert classify_keyword(" stopall ") == "stop"
    assert classify_keyword("UNSUBSCRIBE") == "stop"
    assert classify_keyword("CANCEL") == "stop"
    assert classify_keyword("END") == "stop"
    assert classify_keyword("QUIT") == "stop"
    assert classify_keyword("HELP") == "help"
    assert classify_keyword("help me") is None
    assert classify_keyword("swap july 8") is None


def test_stop_sends_confirmation_and_creates_no_override(session_fixture) -> None:
    runner, sms = _build_runner(session_fixture)

    result = runner.handle_sms(
        message_sid="SM-stop-1",
        from_phone="+15550001",
        body="STOP",
    )

    assert result["status"] == "ok"
    assert result["reason"] == "opt_out"
    assert any("opted out" in body.lower() for _, body in sms.sent)
    overrides = session_fixture.exec(select(OverrideTable)).all()
    assert overrides == []


def test_help_sends_help_text_and_creates_no_override(session_fixture) -> None:
    runner, sms = _build_runner(session_fixture)

    result = runner.handle_sms(
        message_sid="SM-help-1",
        from_phone="+15550001",
        body="HELP",
    )

    assert result["status"] == "ok"
    assert result["reason"] == "help"
    assert any("stop" in body.lower() for _, body in sms.sent)
    overrides = session_fixture.exec(select(OverrideTable)).all()
    assert overrides == []
