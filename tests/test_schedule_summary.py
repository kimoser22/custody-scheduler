"""Turning a run of days into one sentence a parent can read on a phone.

The answer has to survive being a text message: no tables, no per-day list for a
week, and a hard ceiling so one question cannot produce a five-segment SMS.
"""

from datetime import date, timedelta

from core.models import DailyCustodyState, ParentRole
from core.schedule_summary import MAX_QUERY_DAYS, summarize_custody

A = ParentRole.PARENT_A
B = ParentRole.PARENT_B


def _days(start: date, parents: list[ParentRole]) -> list[DailyCustodyState]:
    return [
        DailyCustodyState(
            current_date=start + timedelta(days=offset),
            baseline_parent=parent,
            final_parent=parent,
            is_overridden=False,
        )
        for offset, parent in enumerate(parents)
    ]


def test_single_day_reads_as_a_sentence() -> None:
    summary = summarize_custody(_days(date(2026, 8, 15), [A]))
    assert summary == "Parent A has the kids on 2026-08-15."


def test_uninterrupted_run_collapses_to_one_span() -> None:
    summary = summarize_custody(_days(date(2026, 8, 15), [A, A, A]))
    assert summary == "2026-08-15 to 2026-08-17: Parent A."


def test_handoff_mid_range_names_both_in_order() -> None:
    summary = summarize_custody(_days(date(2026, 8, 15), [A, A, B]))
    assert summary == "2026-08-15 to 2026-08-16: Parent A. 2026-08-17: Parent B."


def test_alternating_days_do_not_collapse() -> None:
    summary = summarize_custody(_days(date(2026, 8, 15), [A, B, A]))
    assert summary == (
        "2026-08-15: Parent A. 2026-08-16: Parent B. 2026-08-17: Parent A."
    )


def test_empty_range_says_so_rather_than_returning_nothing() -> None:
    assert summarize_custody([]) == "I couldn't find any schedule for those dates."


def test_overlong_range_is_capped_and_says_so() -> None:
    """A month-long question must not turn into a wall of segments."""
    summary = summarize_custody(_days(date(2026, 8, 1), [A] * 40))

    assert str(date(2026, 8, 1)) in summary
    assert str(date(2026, 8, 1) + timedelta(days=MAX_QUERY_DAYS - 1)) in summary
    assert "2026-09" not in summary
    assert "full calendar" in summary.lower()


def test_cap_boundary_is_not_truncated() -> None:
    """Exactly at the ceiling is a complete answer, not a truncated one."""
    summary = summarize_custody(_days(date(2026, 8, 1), [A] * MAX_QUERY_DAYS))
    assert "full calendar" not in summary.lower()
