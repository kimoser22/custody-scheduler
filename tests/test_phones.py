"""Phone normalization for SMS opt-out and sender lookup keys."""

from concierge.phones import normalize_phone


def test_normalize_phone_us_and_project_variants() -> None:
    assert normalize_phone("+15550001") == "+15550001"
    assert normalize_phone("15550001") == "+15550001"
    assert normalize_phone("1-555-0001") == "+15550001"
    assert normalize_phone("5550001234") == "+15550001234"
    assert normalize_phone("+1 (555) 000-1234") == "+15550001234"
    assert normalize_phone("+44 7911 123456") == "+447911123456"
