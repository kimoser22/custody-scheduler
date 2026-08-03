"""Phone normalization for SMS opt-out and sender lookup keys."""

from concierge.phones import normalize_phone


def test_normalize_phone_us_and_project_variants() -> None:
    assert normalize_phone("+15550001") == "+15550001"
    assert normalize_phone("15550001") == "+15550001"
    assert normalize_phone("1-555-0001") == "+15550001"
    assert normalize_phone("5550001234") == "+15550001234"
    assert normalize_phone("+1 (555) 000-1234") == "+15550001234"
    assert normalize_phone("+44 7911 123456") == "+447911123456"


def test_ten_digits_gain_the_us_country_code() -> None:
    """The only length that is special: a bare US local number."""
    assert normalize_phone("5551234567") == "+15551234567"


def test_other_lengths_are_prefixed_without_a_country_code() -> None:
    """Everything that is not ten digits keeps its digits as given. Pins the
    behavior of the leading-1 and leading-+ cases, which take the same path."""
    assert normalize_phone("15551234567") == "+15551234567"  # leading 1
    assert normalize_phone("+15551234567") == "+15551234567"  # leading +
    assert normalize_phone("442071234567") == "+442071234567"  # neither
    assert normalize_phone("5550001") == "+5550001"  # short, neither


def test_normalization_is_idempotent() -> None:
    """Opt-out rows are keyed on the normalized value, so normalizing an
    already-normalized number must not change it."""
    for raw in ("5551234567", "+1 (555) 000-1234", "1-555-0001", "+44 7911 123456"):
        once = normalize_phone(raw)
        assert normalize_phone(once) == once


def test_input_without_digits_is_returned_stripped() -> None:
    assert normalize_phone("  not-a-number  ") == "not-a-number"
