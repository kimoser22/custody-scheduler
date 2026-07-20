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
