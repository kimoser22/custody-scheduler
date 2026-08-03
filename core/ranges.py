"""Inclusive date-range helpers for schedule overrides."""

from datetime import date

from core.models import ScheduleOverride

# Activation writes one active_custody_days row per covered day, so an
# absurd span (a typo'd year) should be refused at the edge rather than
# expanded. Shared by the web validator and both SMS parsers so there is one
# definition of "too long" rather than three.
MAX_RANGE_DAYS = 366


def is_valid_range(start: date, end: date | None) -> bool:
    """True when end is absent (single day) or forms a sane inclusive span."""
    if end is None:
        return True
    if end < start:
        return False
    return (end - start).days <= MAX_RANGE_DAYS


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
