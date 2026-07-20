"""Signed auth tokens: HMAC-SHA256 over {uid, role, exp}, fail closed."""

import pytest

from api.auth_tokens import TokenError, mint_token, verify_token


def test_round_trip_recovers_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_SIGNING_SECRET", "s3cret")
    token = mint_token(user_id=101, role="Parent", ttl_seconds=3600, now=1000.0)
    assert verify_token(token, now=1000.0) == (101, "Parent")


def test_signature_binds_to_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_SIGNING_SECRET", "s3cret")
    token = mint_token(user_id=101, role="Parent", now=1000.0)
    monkeypatch.setenv("AUTH_SIGNING_SECRET", "different-secret")
    with pytest.raises(TokenError):
        verify_token(token, now=1000.0)


def test_tampered_signature_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_SIGNING_SECRET", "s3cret")
    token = mint_token(user_id=101, role="Parent", now=1000.0)
    tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    with pytest.raises(TokenError):
        verify_token(tampered, now=1000.0)


def test_tampered_payload_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Flipping the claims without re-signing must not verify — an attacker
    cannot promote themselves from Viewer to Parent."""
    monkeypatch.setenv("AUTH_SIGNING_SECRET", "s3cret")
    viewer = mint_token(user_id=2, role="Viewer", now=1000.0)
    body, sig = viewer.split(".", 1)
    forged_body = mint_token(user_id=101, role="Parent", now=1000.0).split(".", 1)[0]
    with pytest.raises(TokenError):
        verify_token(f"{forged_body}.{sig}", now=1000.0)


def test_malformed_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_SIGNING_SECRET", "s3cret")
    for junk in ["", "no-dot", "parent:a", "a.b.c"]:
        with pytest.raises(TokenError):
            verify_token(junk, now=1000.0)


def test_expired_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_SIGNING_SECRET", "s3cret")
    token = mint_token(user_id=101, role="Parent", ttl_seconds=60, now=1000.0)
    with pytest.raises(TokenError):
        verify_token(token, now=2000.0)


def test_missing_secret_fails_closed_on_verify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUTH_SIGNING_SECRET", raising=False)
    with pytest.raises(TokenError):
        verify_token("anything.here", now=1000.0)


def test_missing_secret_fails_closed_on_mint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUTH_SIGNING_SECRET", raising=False)
    with pytest.raises(TokenError):
        mint_token(user_id=101, role="Parent")
