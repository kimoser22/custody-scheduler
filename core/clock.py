"""The household's calendar date.

This app stores every *instant* as UTC — audit timestamps, override expiry,
decision times — and that is right and stays that way. But "what day is it?" is
a different question, and it is a local-civil-time one. The family is in
Arlington, VA; for four hours every summer evening (five in winter) UTC has
already rolled over to the next day while the parents have not.

That gap is not theoretical: the SMS parser is handed a date and told it is
today, so a request to swap "tomorrow" resolved a day late every evening, and
did so silently. Anything asking for a calendar date should come here; anything
recording a moment in time should keep using UTC directly.

One timezone for the whole household, since everyone is in the same place.
HOUSEHOLD_TIMEZONE overrides it if that ever stops being true.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_HOUSEHOLD_TIMEZONE = "America/New_York"


def resolve_household_timezone() -> ZoneInfo:
    name = os.getenv("HOUSEHOLD_TIMEZONE", "").strip() or DEFAULT_HOUSEHOLD_TIMEZONE
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        # Falling back to UTC would quietly restore the off-by-one day this
        # module exists to prevent, so a typo has to be loud.
        raise ValueError(
            f"HOUSEHOLD_TIMEZONE is not a valid IANA timezone: {name!r}"
        ) from exc


def household_today(now: datetime | None = None) -> date:
    """The calendar date in the household's timezone at `now` (default: this
    instant). Naive datetimes are read as UTC, matching how this codebase
    stores them."""
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(resolve_household_timezone()).date()
