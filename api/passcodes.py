"""Salted passcode hashing for login credentials.

Stored form: ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``. Verification
is constant-time and returns False (never raises) for missing or malformed
stored values, so callers can treat "no credential set" as "login denied".
"""

from __future__ import annotations

import hashlib
import hmac
import os

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 240_000
_SALT_BYTES = 16


def _derive(passcode: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256", passcode.encode("utf-8"), salt, iterations
    )


def hash_passcode(passcode: str, *, iterations: int = _ITERATIONS) -> str:
    salt = os.urandom(_SALT_BYTES)
    digest = _derive(passcode, salt, iterations)
    return f"{_ALGORITHM}${iterations}${salt.hex()}${digest.hex()}"


def verify_passcode(passcode: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algorithm, iterations_raw, salt_hex, digest_hex = stored.split("$")
        if algorithm != _ALGORITHM:
            return False
        iterations = int(iterations_raw)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False

    candidate = _derive(passcode, salt, iterations)
    return hmac.compare_digest(candidate, expected)
