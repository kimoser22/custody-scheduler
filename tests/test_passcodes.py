"""Passcode hashing: PBKDF2-HMAC-SHA256, salted, constant-time verify."""

from api.passcodes import hash_passcode, verify_passcode


def test_hash_then_verify_succeeds() -> None:
    stored = hash_passcode("correct horse")
    assert verify_passcode("correct horse", stored) is True


def test_wrong_passcode_fails() -> None:
    stored = hash_passcode("correct horse")
    assert verify_passcode("battery staple", stored) is False


def test_hashes_are_salted_but_both_verify() -> None:
    a = hash_passcode("same")
    b = hash_passcode("same")
    assert a != b
    assert verify_passcode("same", a) is True
    assert verify_passcode("same", b) is True


def test_verify_against_missing_hash_is_false() -> None:
    assert verify_passcode("anything", None) is False
    assert verify_passcode("anything", "") is False


def test_verify_against_malformed_hash_is_false() -> None:
    assert verify_passcode("anything", "not-a-valid-hash-format") is False
