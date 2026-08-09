"""The household's calendar date, which is not UTC's.

The family is in Arlington, VA. For four to five hours every evening, UTC has
already rolled over to the next day while the parents have not — so anything
that asks "what is today?" in UTC is simply wrong during exactly the hours
people text about tomorrow.

Instants (audit timestamps, expiry) stay UTC everywhere. This module is only
about the *calendar date*, which is a local-civil-time question.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core.clock import (
    DEFAULT_HOUSEHOLD_TIMEZONE,
    household_today,
    resolve_household_timezone,
)

EDT = timezone(timedelta(hours=-4))  # Eastern daylight time (summer)
EST = timezone(timedelta(hours=-5))  # Eastern standard time (winter)


def test_late_summer_evening_is_still_the_same_day() -> None:
    """The bug: 21:30 on the 12th in Arlington is already the 13th in UTC."""
    evening = datetime(2026, 8, 12, 21, 30, tzinfo=EDT)
    assert evening.astimezone(timezone.utc).date().isoformat() == "2026-08-13"

    assert household_today(evening).isoformat() == "2026-08-12"


def test_late_winter_evening_is_still_the_same_day() -> None:
    """Winter is worse: the wrong window opens an hour earlier."""
    evening = datetime(2026, 1, 20, 19, 30, tzinfo=EST)
    assert evening.astimezone(timezone.utc).date().isoformat() == "2026-01-21"

    assert household_today(evening).isoformat() == "2026-01-20"


def test_midday_is_unaffected() -> None:
    """The fix must be narrow — most of the day UTC and Eastern already agree."""
    midday = datetime(2026, 8, 12, 12, 0, tzinfo=EDT)
    assert household_today(midday).isoformat() == "2026-08-12"


def test_accepts_a_naive_utc_instant() -> None:
    """Callers hold naive UTC datetimes all over this codebase; treating one as
    local time would silently reintroduce the bug it is meant to fix."""
    naive_utc = datetime(2026, 8, 13, 1, 30)  # == 21:30 EDT on the 12th

    assert household_today(naive_utc).isoformat() == "2026-08-12"


def test_defaults_to_eastern() -> None:
    assert DEFAULT_HOUSEHOLD_TIMEZONE == "America/New_York"
    assert str(resolve_household_timezone()) == "America/New_York"


def test_timezone_is_env_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOUSEHOLD_TIMEZONE", "America/Los_Angeles")
    assert str(resolve_household_timezone()) == "America/Los_Angeles"

    evening = datetime(2026, 8, 12, 21, 30, tzinfo=timezone(timedelta(hours=-7)))
    assert household_today(evening).isoformat() == "2026-08-12"


def test_invalid_timezone_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    """Falling back to UTC on a typo would restore the original bug quietly,
    which is the one outcome worse than crashing at boot."""
    monkeypatch.setenv("HOUSEHOLD_TIMEZONE", "Mars/Olympus_Mons")

    with pytest.raises(ValueError, match="HOUSEHOLD_TIMEZONE"):
        resolve_household_timezone()


def test_dst_transitions_resolve() -> None:
    """Spring forward and fall back are the classic places a naive offset breaks;
    ZoneInfo handles them, so this pins that we are using it rather than a
    hardcoded -4 or -5."""
    # 2026-03-08 02:00 EST -> 03:00 EDT. 07:30 UTC is 02:30 local-ish, same day.
    spring = datetime(2026, 3, 8, 7, 30, tzinfo=timezone.utc)
    assert household_today(spring).isoformat() == "2026-03-08"

    # 2026-11-01 fall back. 04:30 UTC is 00:30 EDT, still the 1st.
    autumn = datetime(2026, 11, 1, 4, 30, tzinfo=timezone.utc)
    assert household_today(autumn).isoformat() == "2026-11-01"
