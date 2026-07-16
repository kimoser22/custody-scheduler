from datetime import date

from concierge.adapters import HeuristicIntentParser
from core.models import ParentRole


def test_heuristic_parser_reads_iso_date_and_parent():
    parser = HeuristicIntentParser()
    intent = parser.parse("Please swap 2026-08-15 to Parent B for soccer")
    assert intent.override_date == date(2026, 8, 15)
    assert intent.assigned_parent == ParentRole.PARENT_B
    assert "soccer" in intent.reason.lower() or intent.reason


def test_heuristic_parser_ignores_calendar_invalid_date_shaped_token():
    parser = HeuristicIntentParser()
    # "2026-13-40" is 10 chars with dashes in the right spots but is not a
    # real calendar date — must not raise, should fall back to the default.
    intent = parser.parse("swap on ref-no-2026-13-40 for Parent B")
    assert intent.override_date == date(2026, 7, 8)
    assert intent.assigned_parent == ParentRole.PARENT_B


def test_heuristic_parser_uses_first_valid_date_after_an_invalid_one():
    parser = HeuristicIntentParser()
    intent = parser.parse("swap xxxx-yy-zz then really 2026-09-01 for Parent B")
    assert intent.override_date == date(2026, 9, 1)
