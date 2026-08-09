"""An unrecognized reply must not decide a pending swap.

The handshake asked "Reply YES to send to the other parent, or NO to cancel",
then treated *anything* that did not start with YES as NO — so a parent who
answered "wait, who has Friday?" silently lost their request. Same on the
counterparty side, where anything but ACCEPT was a denial.

That was survivable while the only thing you could text was a swap request. It
stops being survivable once the concierge invites questions, so an unrecognized
reply now re-prompts and leaves the request open. It still expires on its own
TTL, which is what bounds the loop.
"""

from datetime import date, datetime, timezone

from langgraph.types import Command

from concierge.graph import build_concierge_graph
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
from core.models import OverrideStatus, ParentRole

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)
INITIATOR = "+15550001"
COUNTERPARTY = "+15550002"


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
                INITIATOR: ResolvedSender(
                    user_id=101,
                    family_id=1,
                    role="Parent",
                    phone=INITIATOR,
                    custody_label="Parent A",
                ),
                COUNTERPARTY: ResolvedSender(
                    user_id=102,
                    family_id=1,
                    role="Parent",
                    phone=COUNTERPARTY,
                    custody_label="Parent B",
                ),
            }
        ),
        overrides=SqlOverrideRepository(session_fixture),
        audit=SqlAuditRepository(session_fixture),
        idempotency=InMemoryIdempotencyStore(),
        now=NOW,
        counterparty_by_family={1: (102, COUNTERPARTY, "Parent B")},
    )
    return build_concierge_graph(deps), deps, sms


def _open_handshake(graph, thread: str):
    return graph.invoke(
        {
            "message_sid": f"SM-{thread}",
            "inbound_from": INITIATOR,
            "inbound_body": "swap july 8 to Parent B",
        },
        config={"configurable": {"thread_id": thread}},
    )


# --- initiator ----------------------------------------------------------------


def test_unrecognized_initiator_reply_keeps_the_request_open(
    session_fixture,
) -> None:
    """The bug. A question mid-handshake used to cancel the swap outright."""
    graph, deps, sms = _build(session_fixture)
    config = {"configurable": {"thread_id": "t-unrecognized"}}
    opened = _open_handshake(graph, "t-unrecognized")
    override_id = opened["override_id"]

    after = graph.invoke(
        Command(resume="wait, who has the kids friday?"), config=config
    )

    override = deps.overrides.get(override_id)
    assert override is not None
    assert override.status == OverrideStatus.DRAFT
    assert "__interrupt__" in after
    assert not any("cancelled" in body.lower() for _, body in sms.sent)


def test_unrecognized_reply_then_yes_still_completes(session_fixture) -> None:
    """Re-prompting is only useful if the handshake survives it."""
    graph, deps, sms = _build(session_fixture)
    config = {"configurable": {"thread_id": "t-recover"}}
    opened = _open_handshake(graph, "t-recover")
    override_id = opened["override_id"]

    graph.invoke(Command(resume="huh?"), config=config)
    graph.invoke(Command(resume="YES"), config=config)
    graph.invoke(Command(resume="ACCEPT"), config=config)

    override = deps.overrides.get(override_id)
    assert override is not None
    assert override.status == OverrideStatus.APPROVED
    assert override.is_active is True


def test_explicit_no_still_cancels(session_fixture) -> None:
    graph, deps, sms = _build(session_fixture)
    config = {"configurable": {"thread_id": "t-no"}}
    opened = _open_handshake(graph, "t-no")

    graph.invoke(Command(resume="NO"), config=config)

    override = deps.overrides.get(opened["override_id"])
    assert override is not None
    assert override.status == OverrideStatus.REJECTED
    assert any("cancelled" in body.lower() for _, body in sms.sent)


def test_initiator_synonyms_and_case(session_fixture) -> None:
    """Real people type 'y', 'ok', 'cancel'. Only the vocabulary decides."""
    for reply, expected in (
        ("y", OverrideStatus.PENDING),
        ("ok", OverrideStatus.PENDING),
        (" Yes ", OverrideStatus.PENDING),
        ("cancel", OverrideStatus.REJECTED),
        ("n", OverrideStatus.REJECTED),
    ):
        graph, deps, _ = _build(session_fixture)
        thread = f"t-syn-{reply.strip()}"
        opened = _open_handshake(graph, thread)
        graph.invoke(
            Command(resume=reply), config={"configurable": {"thread_id": thread}}
        )
        override = deps.overrides.get(opened["override_id"])
        assert override is not None, reply
        assert override.status == expected, f"{reply!r} -> {override.status}"


# --- counterparty -------------------------------------------------------------


def _reach_counterparty(graph, thread: str):
    opened = _open_handshake(graph, thread)
    graph.invoke(
        Command(resume="YES"), config={"configurable": {"thread_id": thread}}
    )
    return opened


def test_unrecognized_counterparty_reply_keeps_the_request_pending(
    session_fixture,
) -> None:
    graph, deps, sms = _build(session_fixture)
    config = {"configurable": {"thread_id": "t-cp-unrecognized"}}
    opened = _reach_counterparty(graph, "t-cp-unrecognized")

    after = graph.invoke(Command(resume="what's this about?"), config=config)

    override = deps.overrides.get(opened["override_id"])
    assert override is not None
    assert override.status == OverrideStatus.PENDING
    assert override.is_active is False
    assert "__interrupt__" in after


def test_explicit_deny_still_rejects(session_fixture) -> None:
    graph, deps, _ = _build(session_fixture)
    config = {"configurable": {"thread_id": "t-cp-deny"}}
    opened = _reach_counterparty(graph, "t-cp-deny")

    graph.invoke(Command(resume="DENY"), config=config)

    override = deps.overrides.get(opened["override_id"])
    assert override is not None
    assert override.status == OverrideStatus.REJECTED
    assert override.is_active is False
