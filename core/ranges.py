"""Inclusive date-range helpers for schedule overrides."""

from datetime import date

from core.models import ScheduleOverride


def effective_end(override: ScheduleOverride) -> date:
    """Inclusive end; omitted end_date means a single-day override."""
    if override.end_date is None:
        return override.override_date
    return override.end_date


def override_covers(override: ScheduleOverride, day: date) -> bool:
    return override.override_date <= day <= effective_end(override)


def ranges_overlap(
    a_start: date, a_end: date, b_start: date, b_end: date
) -> bool:
    return a_start <= b_end and b_start <= a_end
