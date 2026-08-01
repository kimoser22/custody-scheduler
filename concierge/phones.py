"""Normalize inbound phone strings to a consistent E.164-ish key."""


def normalize_phone(phone: str) -> str:
    """Strip separators; prefer +E.164 for US 10/11-digit numbers.

    Opt-out rows and sender lookup share this key so Twilio ``From`` and
    seeded user phones match even when formatting differs (spaces, dashes,
    missing ``+``).
    """
    stripped = phone.strip()
    digits = "".join(ch for ch in stripped if ch.isdigit())
    if not digits:
        return stripped
    if len(digits) == 10:
        return f"+1{digits}"
    if digits.startswith("1") or stripped.startswith("+"):
        return f"+{digits}"
    return f"+{digits}"
