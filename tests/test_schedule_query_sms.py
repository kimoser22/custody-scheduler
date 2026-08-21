"""Answering "who has the kids on X?" over SMS.

A query is a read: one turn, no counterparty, no consent, and nothing written.
The load-bearing assertions here are the negative ones — that asking a question
creates no override row and leaves no open handshake behind — because the
failure that would matter is a question quietly booking a custody handoff.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from concierge.factory import build_default_runner
from concierge.repos import SqlScheduleReader
from core.models import OverrideStatus, OverrideType, ParentRole
from database.schema import (
    BaselineTable,
    FamilyLink,
    HandshakeThreadTable,
    OverrideTable,
    UserTable,
)

NOW = datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)
PARENT_A_PHONE = "+15550001"
PARENT_B_PHONE = "+15550002"
STRANGER = "+19998887777"

# Epoch 2026-01-05 with Parent A starting; the 2-2-3 cycle is 14 days.
FAMILY_ID = 1


@pytest.fixture(name="family")
def _family(session_fixture: Session) -> None:
    session_fixture.add(
        BaselineTable(
            family_id=FAMILY_ID,
            epoch_start_date=date(2026, 1, 5),
            starting_parent=ParentRole.PARENT_A.value,
        )
    )
    session_fixture.add(
        UserTable(
            id=101,
            family_id=FAMILY_ID,
            role="Parent",
            phone=PARENT_A_PHONE,
            custody_label="Parent A",
        )
    )
    session_fixture.add(
        UserTable(
            id=102,
            family_id=FAMILY_ID,
            role="Parent",
            phone=PARENT_B_PHONE,
            custody_label="Parent B",
        )
    )
    session_fixture.commit()


def _ask(session: Session, body: str, *, sid: str, frm: str = PARENT_A_PHONE):
    runner = build_default_runner(session=session, now=NOW)
    sent: list[tuple[str, str]] = []

    class Recording:
        def send(self, to: str, body: str) -> None:
            sent.append((to, body))

        def send_forced(self, to: str, body: str) -> None:
            sent.append((to, body))

    runner.deps.sms = Recording()
    result = runner.handle_sms(message_sid=sid, from_phone=frm, body=body)
    return result, sent, runner


def _overrides(session: Session) -> list[OverrideTable]:
    return list(session.exec(select(OverrideTable)).all())


def test_single_date_query_is_answered_and_writes_nothing(
    session_fixture: Session, family: None
) -> None:
    result, sent, runner = _ask(
        session_fixture, "who has the kids on 2026-08-15?", sid="SM-q1"
    )

    assert result["status"] == "ok"
    assert len(sent) == 1
    to, body = sent[0]
    assert to == PARENT_A_PHONE
    # Assert the answer *shape*, not just that a date appears: the clarification
    # copy quotes "swap 2026-08-15 to Parent B" as its example, so a looser
    # check would pass even if the query had failed to parse.
    assert body == "Parent A has the kids on 2026-08-15." or body == (
        "Parent B has the kids on 2026-08-15."
    )
    assert "couldn't understand" not in body

    # The whole point: a question must not become a schedule change.
    assert _overrides(session_fixture) == []
    assert runner.registry.get(PARENT_A_PHONE) is None
    assert session_fixture.get(HandshakeThreadTable, PARENT_A_PHONE) is None


def test_range_query_crossing_a_handoff_names_both_parents(
    session_fixture: Session, family: None
) -> None:
    """A 2-2-3 cycle guarantees a handoff inside any 5-day window."""
    _, sent, _ = _ask(
        session_fixture,
        "who has them 2026-08-15 to 2026-08-19?",
        sid="SM-q2",
    )

    body = sent[0][1]
    assert "Parent A" in body and "Parent B" in body
    assert _overrides(session_fixture) == []


def test_query_reports_an_approved_override_not_the_baseline(
    session_fixture: Session, family: None
) -> None:
    """An approved swap is the answer for that day — otherwise the text would
    contradict the calendar the parents are looking at."""
    target = date(2026, 8, 15)
    baseline_answer = SqlScheduleReader(session_fixture).custody_between(
        FAMILY_ID, target, target
    )[0].final_parent
    flipped = (
        ParentRole.PARENT_B
        if baseline_answer == ParentRole.PARENT_A
        else ParentRole.PARENT_A
    )
    session_fixture.add(
        OverrideTable(
            family_id=FAMILY_ID,
            override_date=target,
            assigned_parent=flipped.value,
            override_type=OverrideType.MUTUAL_SWAP.value,
            description="approved swap",
            is_active=True,
            status=OverrideStatus.APPROVED.value,
            requested_by_user_id=101,
            expires_at=datetime(2026, 8, 20, 12, 0),
        )
    )
    session_fixture.commit()

    _, sent, _ = _ask(session_fixture, "who has the kids 2026-08-15?", sid="SM-q3")

    assert flipped.value in sent[0][1]
    assert baseline_answer.value not in sent[0][1]


def test_query_from_an_unknown_number_is_ignored(
    session_fixture: Session, family: None
) -> None:
    """Custody detail must never reach a number that is not in the family."""
    result, sent, _ = _ask(
        session_fixture,
        "who has the kids on 2026-08-15?",
        sid="SM-q4",
        frm=STRANGER,
    )

    assert result["status"] == "ignored"
    assert sent == []


def test_sms_answer_agrees_with_the_http_schedule(
    session_fixture: Session,
    client_fixture: TestClient,
    family: None,
) -> None:
    """The anti-drift guard: both surfaces load the schedule through
    database/schedule_reads.py, so they cannot answer differently."""
    _, sent, _ = _ask(session_fixture, "who has the kids 2026-08-15?", sid="SM-q5")
    sms_body = sent[0][1]

    from api.dependencies import get_current_user
    from main import app

    async def _viewer():
        return UserTable(id=101, family_id=FAMILY_ID, role="Parent")

    app.dependency_overrides[get_current_user] = _viewer
    response = client_fixture.get(
        "/api/v1/schedule/",
        params={"start_date": "2026-08-15", "end_date": "2026-08-15"},
    )
    assert response.status_code == 200
    http_parent = response.json()[0]["final_parent"]

    assert http_parent in sms_body


def test_a_swap_request_still_creates_a_draft(
    session_fixture: Session, family: None
) -> None:
    """The query branch must not have swallowed the write path."""
    _, sent, _ = _ask(
        session_fixture, "swap 2026-08-15 to Parent B for soccer", sid="SM-q6"
    )

    rows = _overrides(session_fixture)
    assert len(rows) == 1
    assert rows[0].status == OverrideStatus.DRAFT.value
    assert any("YES" in body for _, body in sent)


# --- next-handoff ("when do I get them back?") ---------------------------------


def test_next_handoff_from_away_parent_names_return_and_writes_nothing(
    session_fixture: Session, family: None
) -> None:
    """On 2026-08-10 Parent B holds through the 11th; Parent A is back the 12–13."""
    result, sent, runner = _ask(
        session_fixture,
        "when do I get them back?",
        sid="SM-nh1",
        frm=PARENT_A_PHONE,
    )

    assert result["status"] == "ok"
    assert len(sent) == 1
    body = sent[0][1]
    assert body == (
        "Parent B has them through 2026-08-11. "
        "Back to you 2026-08-12 to 2026-08-13."
    )

    assert _overrides(session_fixture) == []
    assert runner.registry.get(PARENT_A_PHONE) is None
    assert session_fixture.get(HandshakeThreadTable, PARENT_A_PHONE) is None


def test_next_handoff_from_holding_parent_orients_as_you_have(
    session_fixture: Session, family: None
) -> None:
    result, sent, runner = _ask(
        session_fixture,
        "when do I get them back?",
        sid="SM-nh2",
        frm=PARENT_B_PHONE,
    )

    assert result["status"] == "ok"
    assert sent[0][1] == (
        "You have the kids through 2026-08-11. "
        "Parent A has them starting 2026-08-12."
    )
    assert _overrides(session_fixture) == []
    assert session_fixture.get(HandshakeThreadTable, PARENT_B_PHONE) is None


def test_next_handoff_from_unknown_number_is_ignored(
    session_fixture: Session, family: None
) -> None:
    result, sent, _ = _ask(
        session_fixture,
        "when do I get them back?",
        sid="SM-nh3",
        frm=STRANGER,
    )
    assert result["status"] == "ignored"
    assert sent == []


def test_next_handoff_agrees_with_schedule_reader_ground_truth(
    session_fixture: Session, family: None
) -> None:
    from core.clock import household_today
    from core.schedule_summary import HANDOFF_HORIZON_DAYS, next_handoff_summary

    start = household_today(NOW)
    end = start + timedelta(days=HANDOFF_HORIZON_DAYS)
    days = SqlScheduleReader(session_fixture).custody_between(FAMILY_ID, start, end)
    expected = next_handoff_summary(days, "Parent A")

    _, sent, _ = _ask(
        session_fixture,
        "when are they back",
        sid="SM-nh4",
        frm=PARENT_A_PHONE,
    )
    assert sent[0][1] == expected
