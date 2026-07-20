from datetime import date, datetime, timezone

from langgraph.types import Command

from core.models import OverrideStatus, ParentRole
from concierge.graph import build_concierge_graph, resolve_thread_id
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


NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)


def _build(session_fixture):
    sms = FakeSmsGateway()
    deps = ConciergeDeps(
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
    )
    graph = build_concierge_graph(deps)
    return graph, deps, sms


def test_resolve_thread_id_prefers_override():
    assert resolve_thread_id(family_id=1, override_id=9, phone="+1") == (
        "family:1:override:9"
    )
    assert resolve_thread_id(family_id=1, override_id=None, phone="+1") == (
        "family:1:phone:+1"
    )


def test_graph_double_handshake_happy_path(session_fixture) -> None:
    graph, deps, sms = _build(session_fixture)
    config = {"configurable": {"thread_id": "family:1:phone:+15550001"}}

    interrupted = graph.invoke(
        {
            "message_sid": "SMstart",
            "inbound_from": "+15550001",
            "inbound_body": "swap july 8",
        },
        config=config,
    )
    assert "__interrupt__" in interrupted or interrupted.get("current_step") == (
        "awaiting_initiator_confirm"
    )

    after_yes = graph.invoke(Command(resume="YES"), config=config)
    assert "__interrupt__" in after_yes or after_yes.get("current_step") == (
        "awaiting_counterparty_consent"
    )

    final = graph.invoke(Command(resume="ACCEPT"), config=config)
    override_id = final["override_id"]
    override = deps.overrides.get(override_id)
    assert override is not None
    assert override.status == OverrideStatus.APPROVED
    assert override.is_active is True
    assert final["current_step"] == "completed"
    assert any("Confirmed" in body for _, body in sms.sent)


def test_graph_ends_without_draft_on_unclear_message(session_fixture) -> None:
    """An unparseable inbound message ends the graph immediately — no interrupt,
    no draft — after sending a clarification SMS, rather than fabricating a
    wrong-date/wrong-parent draft and asking the initiator to confirm it."""
    from concierge.ports import FakeIntentParser

    graph, deps, sms = _build(session_fixture)
    deps.parser = FakeIntentParser(None)

    result = graph.invoke(
        {
            "message_sid": "SM-unclear",
            "inbound_from": "+15550001",
            "inbound_body": "hey are you around next week",
        },
        config={"configurable": {"thread_id": "unclear-thread-1"}},
    )

    assert "__interrupt__" not in result
    assert result.get("current_step") == "unparseable"
    assert "override_id" not in result
    assert any("understand" in body.lower() for _, body in sms.sent)


def test_graph_itself_does_not_dedupe_by_message_sid(session_fixture) -> None:
    """message_sid dedup is a transport-boundary concern owned by
    LangGraphConciergeRunner.handle_sms (see
    tests/test_concierge_runner.py), not the graph. A direct caller that
    invokes the same sid twice on two different thread_ids — as the graph
    has no way to know they're "the same" delivery — gets two independent
    drafts, not a drop. This documents that contract so it isn't
    accidentally relied upon at the graph level again."""
    graph, deps, _ = _build(session_fixture)

    first = graph.invoke(
        {
            "message_sid": "SMdup",
            "inbound_from": "+15550001",
            "inbound_body": "swap",
        },
        config={"configurable": {"thread_id": "dup-test-1"}},
    )
    second = graph.invoke(
        {
            "message_sid": "SMdup",
            "inbound_from": "+15550001",
            "inbound_body": "swap again",
        },
        config={"configurable": {"thread_id": "dup-test-2"}},
    )

    assert first.get("dropped") is False
    assert second.get("dropped") is False
    assert first["override_id"] != second["override_id"]
