"""Normalize inbound phone strings to a consistent E.164-ish key."""


def normalize_phone(phone: str) -> str:
    """Strip separators; prefer +E.164 for US 10/11-digit numbers.

    Opt-out rows and sender lookup share this key so Twilio ``From`` and
    seeded user phones match even when formatting differs (spaces, dashes,
    missing ``+``). Idempotent, since callers normalize values that may
    already be normalized.

    US-centric by design: a ten-digit input is assumed to be a US number. A
    non-US *national* format keeps its leading zero (``07700900123`` becomes
    ``+07700900123``), which is wrong as E.164 — pass those in international
    form if this app ever leaves the US.
    """
    stripped = phone.strip()
    digits = "".join(ch for ch in stripped if ch.isdigit())
    if not digits:
        return stripped
    # A bare ten-digit number is the one ambiguous case: assume US and add the
    # country code. Everything else already carries its own, whether or not the
    # sender wrote the leading "+".
    if len(digits) == 10:
        return f"+1{digits}"
    return f"+{digits}"
