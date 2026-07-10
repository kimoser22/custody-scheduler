from collections.abc import Sequence
from datetime import date

from core.models import CustodyDay, HolidayOverride, ScheduleRule


def calculate_schedule(
    start_date: date,
    end_date: date,
    rules: Sequence[ScheduleRule],
    holiday_overrides: Sequence[HolidayOverride],
) -> list[CustodyDay]:
    ...
