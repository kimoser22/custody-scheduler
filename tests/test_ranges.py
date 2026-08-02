"""Inclusive date-range helpers for schedule overrides."""

from datetime import date

from core.models import OverrideType, ParentRole, ScheduleOverride
from core.ranges import effective_end, override_covers, ranges_overlap


def test_effective_end_defaults_to_start() -> None:
    override = ScheduleOverride(
        override_date=date(2026, 1, 6),
        assigned_parent=ParentRole.PARENT_B,
        override_type=OverrideType.HOLIDAY,
        description="x",
    )
    assert effective_end(override) == date(2026, 1, 6)


def test_override_covers_inclusive_range() -> None:
    override = ScheduleOverride(
        override_date=date(2026, 1, 6),
        end_date=date(2026, 1, 8),
        assigned_parent=ParentRole.PARENT_B,
        override_type=OverrideType.HOLIDAY,
        description="x",
    )
    assert override_covers(override, date(2026, 1, 5)) is False
    assert override_covers(override, date(2026, 1, 6)) is True
    assert override_covers(override, date(2026, 1, 8)) is True
    assert override_covers(override, date(2026, 1, 9)) is False


def test_ranges_overlap() -> None:
    assert ranges_overlap(
        date(2026, 1, 6), date(2026, 1, 8), date(2026, 1, 8), date(2026, 1, 10)
    )
    assert not ranges_overlap(
        date(2026, 1, 6), date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 9)
    )
