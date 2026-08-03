"""Multi-day swap requests over SMS, end to end through the graph.

The confirmation step is the parent's only chance to catch a misread request
before the other parent is asked to approve it. If the copy echoes just the
start date, a ten-day vacation that was silently truncated to one day looks
identical to a correct single-day swap — so these tests assert the span appears
in every message, not only that the draft carries it.
"""

from datetime import date, datetime, timezone

import pytest
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
from concierge.runner import LangGraphConciergeRunner
from core.models import OverrideStatus, ParentRole
from database.schema import OverrideTable

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)
INITIATOR = "+15550001"
COUNTERPARTY = "+15550002"

START = date(2026, 8, 1)
END = date(2026, 8, 10)
SPAN = "2026-08-01 to 2026-08-10"


def _runner(session_fixture, intent: ParsedIntent):
    sms = FakeSmsGateway()
    deps = ConciergeDeps(
        sms=sms,
        parser=FakeIntentParser(intent),
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
        parents_by_family={
            1: [(101, INITIATOR, "Parent A"), (102, COUNTERPARTY, "Parent B")]
        },
    )
    return LangGraphConciergeRunner(deps=deps), sms


@pytest.fixture(name="range_intent")
def _range_intent() -> ParsedIntent:
    return ParsedIntent(
        override_date=START,
        end_date=END,
        assigned_parent=ParentRole.PARENT_B,
        reason="vacation",
    )


def _bodies(sms: FakeSmsGateway) -> str:
    return "\n".join(body for _, body in sms.sent)


def test_range_request_creates_a_draft_spanning_both_dates(
    session_fixture, range_intent: ParsedIntent
) -> None:
    runner, _ = _runner(session_fixture, range_intent)

    runner.handle_sms(
        message_sid="SM-range-1",
        from_phone=INITIATOR,
        body="swap 2026-08-01 to 2026-08-10 to Parent B for vacation",
    )

    draft = session_fixture.exec(select(OverrideTable)).one()
    assert draft.override_date == START
    assert draft.end_date == END


def test_confirmation_sms_shows_the_full_span(
    session_fixture, range_intent: ParsedIntent
) -> None:
    """The safety net: the requester must be able to see the whole range before
    replying YES."""
    runner, sms = _runner(session_fixture, range_intent)

    runner.handle_sms(
        message_sid="SM-range-2",
        from_phone=INITIATOR,
        body="swap 2026-08-01 to 2026-08-10 to Parent B",
    )

    assert SPAN in _bodies(sms)


def test_proposal_and_final_confirmation_show_the_full_span(
    session_fixture, range_intent: ParsedIntent
) -> None:
    """The counterparty approves what they can see; a start-date-only proposal
    would have them consenting to an invisible ten-day block."""
    runner, sms = _runner(session_fixture, range_intent)

    runner.handle_sms(
        message_sid="SM-range-3",
        from_phone=INITIATOR,
        body="swap 2026-08-01 to 2026-08-10 to Parent B",
    )
    sms.sent.clear()
    runner.handle_sms(message_sid="SM-range-4", from_phone=INITIATOR, body="YES")
    proposal = _bodies(sms)

    sms.sent.clear()
    final = runner.handle_sms(
        message_sid="SM-range-5", from_phone=COUNTERPARTY, body="ACCEPT"
    )

    assert SPAN in proposal
    assert SPAN in _bodies(sms)
    assert final["status"] == "ok"

    override = session_fixture.exec(select(OverrideTable)).one()
    assert override.status == OverrideStatus.APPROVED.value
    assert override.is_active is True
    assert override.end_date == END


def test_single_day_copy_is_unchanged(session_fixture) -> None:
    """No stray range suffix when there is only one day."""
    single = ParsedIntent(
        override_date=date(2026, 8, 7),
        assigned_parent=ParentRole.PARENT_B,
        reason="trains",
    )
    runner, sms = _runner(session_fixture, single)

    runner.handle_sms(
        message_sid="SM-single-1",
        from_phone=INITIATOR,
        body="swap 2026-08-07 to Parent B",
    )

    bodies = _bodies(sms)
    assert "2026-08-07" in bodies
    assert " to 2026-08-07" not in bodies
