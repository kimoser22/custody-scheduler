"""Render a stretch of the custody calendar as one readable sentence.

The consumer is an SMS reply, so this collapses consecutive days that share a
parent into spans rather than listing every date: "who has them next week"
should come back as one or two clauses, not seven.

Pure — takes the days the engine already calculated and returns text.
"""

from __future__ import annotations

from core.models import DailyCustodyState, ParentRole
from core.notifications import format_override_dates

# A question can name a wide range; a text message cannot answer one. Beyond
# this many days the reply is capped and points at the web calendar instead.
MAX_QUERY_DAYS = 14

NO_SCHEDULE_FOUND = "I couldn't find any schedule for those dates."


def _runs(
    days: list[DailyCustodyState],
) -> list[tuple[DailyCustodyState, DailyCustodyState]]:
    """Group consecutive days sharing a parent into (first, last) pairs."""
    grouped: list[tuple[DailyCustodyState, DailyCustodyState]] = []
    for day in days:
        if grouped and grouped[-1][1].final_parent == day.final_parent:
            grouped[-1] = (grouped[-1][0], day)
        else:
            grouped.append((day, day))
    return grouped


def _clause(first: DailyCustodyState, last: DailyCustodyState) -> str:
    parent: ParentRole = first.final_parent
    if first.current_date == last.current_date:
        return f"{first.current_date}: {parent.value}"
    span = format_override_dates(first.current_date, last.current_date)
    return f"{span}: {parent.value}"


def summarize_custody(days: list[DailyCustodyState]) -> str:
    if not days:
        return NO_SCHEDULE_FOUND

    ordered = sorted(days, key=lambda day: day.current_date)
    capped = ordered[:MAX_QUERY_DAYS]
    truncated = len(ordered) > MAX_QUERY_DAYS

    runs = _runs(capped)

    # A single day reads better as a sentence than as a "date: parent" clause,
    # and one day is the most common question by far.
    if len(runs) == 1 and capped[0].current_date == capped[-1].current_date:
        body = f"{capped[0].final_parent.value} has the kids on {capped[0].current_date}."
    else:
        body = " ".join(f"{_clause(first, last)}." for first, last in runs)

    if truncated:
        body += (
            f" (Showing the first {MAX_QUERY_DAYS} days — "
            "see the full calendar in the app.)"
        )
    return body
