from datetime import date

import pytest

from core.engine import calculate_schedule
from core.models import HolidayOverride, Parent, ScheduleRule


def test_calculate_schedule_empty_range() -> None:
    pytest.skip("Not implemented")


def test_calculate_schedule_applies_holiday_override() -> None:
    rules = [
        ScheduleRule(
            start_date=date(2026, 1, 1),
            anchor_parent=Parent.PARENT_A,
        )
    ]
    overrides = [
        HolidayOverride(
            date=date(2026, 1, 15),
            parent=Parent.PARENT_B,
            reason="Holiday",
        )
    ]

    _ = calculate_schedule(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        rules=rules,
        holiday_overrides=overrides,
    )

    pytest.skip("Not implemented")
