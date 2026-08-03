from datetime import date

from concierge.adapters import HeuristicIntentParser
from core.models import ParentRole


def test_heuristic_parser_reads_iso_date_and_parent():
    parser = HeuristicIntentParser()
    intent = parser.parse("Please swap 2026-08-15 to Parent B for soccer")
    assert intent is not None
    assert intent.override_date == date(2026, 8, 15)
    assert intent.assigned_parent == ParentRole.PARENT_B
    assert "soccer" in intent.reason.lower()


def test_heuristic_parser_reads_parent_a():
    parser = HeuristicIntentParser()
    intent = parser.parse("move 2026-09-01 to Parent A")
    assert intent is not None
    assert intent.assigned_parent == ParentRole.PARENT_A


def test_heuristic_parser_uses_first_valid_date_after_an_invalid_one():
    parser = HeuristicIntentParser()
    intent = parser.parse("swap xxxx-yy-zz then really 2026-09-01 for Parent B")
    assert intent is not None
    assert intent.override_date == date(2026, 9, 1)


def test_heuristic_parser_returns_none_when_no_valid_date():
    """Fail safe: without a real date, do NOT fabricate one — signal unclear."""
    parser = HeuristicIntentParser()
    assert parser.parse("can you take him sometime next week? Parent B") is None


def test_heuristic_parser_returns_none_for_calendar_invalid_date_shaped_token():
    parser = HeuristicIntentParser()
    # "2026-13-40" is 10 chars with dashes in the right spots but not a real
    # date — and there is no other valid date, so the request is unclear.
    assert parser.parse("swap on ref-no-2026-13-40 for Parent B") is None


def test_heuristic_parser_returns_none_when_parent_not_specified():
    """Ambiguous assignment must not silently default to Parent A."""
    parser = HeuristicIntentParser()
    assert parser.parse("swap 2026-08-15 please") is None


# --- date ranges ---------------------------------------------------------------


def test_two_dates_are_read_as_an_inclusive_range():
    """Regression: the parser used to stop at the first date, so a ten-day
    vacation request silently became a one-day override — and the confirmation
    SMS echoed only the start, so nobody could see what was dropped."""
    parser = HeuristicIntentParser()
    intent = parser.parse("swap 2026-08-01 to 2026-08-10 to Parent B for vacation")
    assert intent is not None
    assert intent.override_date == date(2026, 8, 1)
    assert intent.end_date == date(2026, 8, 10)
    assert intent.assigned_parent == ParentRole.PARENT_B


def test_reversed_dates_are_normalized_to_min_and_max():
    parser = HeuristicIntentParser()
    intent = parser.parse("swap 2026-08-10 to 2026-08-01 to Parent A")
    assert intent is not None
    assert intent.override_date == date(2026, 8, 1)
    assert intent.end_date == date(2026, 8, 10)


def test_single_date_leaves_end_date_unset():
    parser = HeuristicIntentParser()
    intent = parser.parse("swap 2026-08-07 to Parent B")
    assert intent is not None
    assert intent.end_date is None


def test_three_dates_are_ambiguous_and_yield_none():
    """Never guess which two of three dates were meant — ask instead."""
    parser = HeuristicIntentParser()
    assert (
        parser.parse("swap 2026-08-01 2026-08-05 2026-08-10 to Parent B") is None
    )


def test_range_longer_than_the_cap_yields_none():
    """Matches the web validator's ceiling; activation writes a row per day."""
    parser = HeuristicIntentParser()
    assert parser.parse("swap 2026-01-01 to 2027-06-01 to Parent B") is None
