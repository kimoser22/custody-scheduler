"""Pure ICS builder for custody calendar feeds."""

from datetime import date, datetime, timedelta, timezone

from core.models import (
    BaselineSchedule,
    DailyCustodyState,
    OverrideType,
    ParentRole,
    ScheduleOverride,
)
from core.engine import calculate_schedule
from core.ics import PRODID, build_custody_ics, escape_ics_text


def test_escape_ics_text() -> None:
    assert escape_ics_text("a,b;c\\d\ne") == "a\\,b\\;c\\\\d\\ne"


def test_build_custody_ics_has_required_calendar_props() -> None:
    day = DailyCustodyState(
        current_date=date(2026, 1, 6),
        baseline_parent=ParentRole.PARENT_A,
        final_parent=ParentRole.PARENT_A,
        is_overridden=False,
        override_details=None,
    )
    stamped = datetime(2026, 1, 6, 12, 0, tzinfo=timezone.utc)
    ics = build_custody_ics(days=[day], family_id=1, now=stamped)

    assert "BEGIN:VCALENDAR" in ics
    assert "END:VCALENDAR" in ics
    assert "VERSION:2.0" in ics
    assert f"PRODID:{PRODID}" in ics
    assert "CALSCALE:GREGORIAN" in ics
    assert "METHOD:PUBLISH" in ics
    assert "X-WR-CALNAME:Custody Schedule" in ics


def test_build_custody_ics_vevent_fields() -> None:
    day = DailyCustodyState(
        current_date=date(2026, 1, 6),
        baseline_parent=ParentRole.PARENT_A,
        final_parent=ParentRole.PARENT_B,
        is_overridden=True,
        override_details=ScheduleOverride(
            override_date=date(2026, 1, 6),
            assigned_parent=ParentRole.PARENT_B,
            override_type=OverrideType.HOLIDAY,
            description="Special, day; note",
            is_active=True,
        ),
    )
    stamped = datetime(2026, 1, 6, 15, 30, 45, tzinfo=timezone.utc)
    ics = build_custody_ics(days=[day], family_id=1, now=stamped)

    assert "BEGIN:VEVENT" in ics
    assert "END:VEVENT" in ics
    assert "UID:custody-1-20260106@custody-scheduler" in ics
    assert "DTSTAMP:20260106T153045Z" in ics
    assert "DTSTART;VALUE=DATE:20260106" in ics
    assert "DTEND;VALUE=DATE:20260107" in ics
    assert "SUMMARY:Custody: Parent B (Holiday)" in ics
    assert "DESCRIPTION:Special\\, day\\; note" in ics


def test_build_custody_ics_omits_description_when_not_overridden() -> None:
    day = DailyCustodyState(
        current_date=date(2026, 1, 5),
        baseline_parent=ParentRole.PARENT_A,
        final_parent=ParentRole.PARENT_A,
        is_overridden=False,
        override_details=None,
    )
    ics = build_custody_ics(
        days=[day],
        family_id=1,
        now=datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc),
    )
    assert "DESCRIPTION:" not in ics


def test_build_custody_ics_from_engine_schedule() -> None:
    baseline = BaselineSchedule(
        epoch_start_date=date(2026, 1, 5),
        starting_parent=ParentRole.PARENT_A,
    )
    days = calculate_schedule(
        baseline, [], date(2026, 1, 5), date(2026, 1, 5) + timedelta(days=1)
    )
    ics = build_custody_ics(
        days=days,
        family_id=9,
        now=datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc),
    )
    assert ics.count("BEGIN:VEVENT") == 2
    assert "UID:custody-9-20260105@custody-scheduler" in ics
    assert "UID:custody-9-20260106@custody-scheduler" in ics
