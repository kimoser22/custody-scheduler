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

# Look-ahead for "when do I get them back?" — twin of HANDOFF_HORIZON_DAYS in
# frontend/src/lib/nextHandoff.ts. Baseline handoffs land every 2–3 days; 45
# exists so an approved holiday block that blankets weeks still surfaces the
# next transition.
HANDOFF_HORIZON_DAYS = 45

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


def next_handoff_summary(days: list[DailyCustodyState], my_label: str) -> str:
    """Oriented answer for \"when do I get them back?\" over a look-ahead window.

    ``my_label`` is the sender's custody label (e.g. \"Parent A\"). Framing
    changes with who you are; the dates do not.
    """
    if not days:
        return NO_SCHEDULE_FOUND

    ordered = sorted(days, key=lambda day: day.current_date)
    runs = _runs(ordered)
    if not runs:
        return NO_SCHEDULE_FOUND

    labels_present = {first.final_parent.value for first, _ in runs}
    if my_label not in labels_present:
        # Defensive: never crash the webhook if the label is missing from the
        # window — fall back to a neutral span summary.
        return summarize_custody(ordered)

    current_first, current_last = runs[0]
    window_end = ordered[-1].current_date

    if current_first.final_parent.value == my_label:
        if len(runs) == 1:
            return (
                f"{my_label} has the kids through {window_end} — "
                "see the full calendar in the app."
            )
        next_first, _ = runs[1]
        other = next_first.final_parent.value
        return (
            f"You have the kids through {current_last.current_date}. "
            f"{other} has them starting {next_first.current_date}."
        )

    # Away now: current run is the other parent; find the first run that is ours.
    my_run = next(
        ((first, last) for first, last in runs if first.final_parent.value == my_label),
        None,
    )
    assert my_run is not None  # labels_present already checked
    my_first, my_last = my_run
    other = current_first.final_parent.value
    back = format_override_dates(my_first.current_date, my_last.current_date)
    return (
        f"{other} has them through {current_last.current_date}. "
        f"Back to you {back}."
    )
