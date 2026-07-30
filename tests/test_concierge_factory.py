import logging

import pytest
from sqlmodel import Session

from concierge.adapters import HeuristicIntentParser
from concierge.factory import build_default_runner, describe_handshake_durability
from concierge.llm_parser import CompositeIntentParser, LLMIntentParser
from concierge.repos import SqlOverrideRepository
from core.models import OverrideStatus
from database.schema import FamilyLink, UserTable


def test_startup_reports_handshakes_survive_restarts(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Handshakes are checkpointed to the database now, so startup should say
    where that state lives. Logged at WARNING so uvicorn surfaces it on Fly."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:////data/custody.db")
    with caplog.at_level(logging.WARNING):
        describe_handshake_durability()

    warnings = [
        record for record in caplog.records if record.levelno == logging.WARNING
    ]
    messages = [record.getMessage().lower() for record in warnings]
    assert any("durable" in message and "survives restarts" in message for message in messages)
    assert not any("in-memory only" in message for message in messages)


def test_startup_still_warns_when_the_database_is_ephemeral(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An in-memory database cannot checkpoint across connections, so the old
    caveat still applies there and must be stated."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    with caplog.at_level(logging.INFO):
        describe_handshake_durability()

    messages = [record.getMessage().lower() for record in caplog.records]
    assert any(
        "in-memory" in message and "restart" in message for message in messages
    )


def test_handshake_state_persists_across_separate_runner_builds(
    session_fixture: Session,
) -> None:
    """Regression test for the bug where FastAPI's Depends(get_concierge_runner)
    builds a brand-new LangGraphConciergeRunner (fresh in-memory checkpointer +
    thread registry) on every HTTP request, silently discarding a paused
    handshake between the initial SMS and the reply SMS. build_default_runner
    must share checkpoint/registry state across independently-constructed
    runner instances the way separate webhook requests do."""
    session_fixture.add(FamilyLink(id=999, family_name="Isolated Test Family"))
    session_fixture.add(
        UserTable(
            id=9001,
            family_id=999,
            role="Parent",
            phone="+19995550001",
            custody_label="Parent A",
        )
    )
    session_fixture.add(
        UserTable(
            id=9002,
            family_id=999,
            role="Parent",
            phone="+19995550002",
            custody_label="Parent B",
        )
    )
    session_fixture.commit()

    # Each call below mirrors one separate HTTP request: its own runner
    # instance, built fresh, exactly as api.twilio_webhook.get_concierge_runner
    # does via FastAPI's Depends.
    first = build_default_runner(session=session_fixture).handle_sms(
        message_sid="SM-fac-1",
        from_phone="+19995550001",
        body="swap 2026-07-08 to Parent B",
    )
    assert first["status"] == "waiting"

    second = build_default_runner(session=session_fixture).handle_sms(
        message_sid="SM-fac-2", from_phone="+19995550001", body="YES"
    )
    assert second["status"] == "waiting"

    third = build_default_runner(session=session_fixture).handle_sms(
        message_sid="SM-fac-3", from_phone="+19995550002", body="ACCEPT"
    )
    assert third["status"] == "ok"

    override_id = third["result"]["override_id"]
    override = SqlOverrideRepository(session_fixture).get(override_id)
    assert override is not None
    assert override.status == OverrideStatus.APPROVED
    assert override.is_active is True


def test_parser_is_heuristic_only_without_api_key(
    session_fixture: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No ANTHROPIC_API_KEY -> today's behavior exactly; the LLM path (and the
    anthropic dependency) must not be exercised at all."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    runner = build_default_runner(session=session_fixture)
    assert isinstance(runner.deps.parser, HeuristicIntentParser)


def test_parser_is_composite_with_llm_fallback_when_key_set(
    session_fixture: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-dummy")
    runner = build_default_runner(session=session_fixture)
    parser = runner.deps.parser
    assert isinstance(parser, CompositeIntentParser)
    assert isinstance(parser.primary, HeuristicIntentParser)
    assert isinstance(parser.fallback, LLMIntentParser)
    assert parser.fallback.model == "claude-opus-4-8"


def test_llm_model_is_overridable_via_env(
    session_fixture: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-dummy")
    monkeypatch.setenv("CONCIERGE_LLM_MODEL", "claude-haiku-4-5")
    runner = build_default_runner(session=session_fixture)
    assert runner.deps.parser.fallback.model == "claude-haiku-4-5"
