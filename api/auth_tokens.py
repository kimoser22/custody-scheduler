"""Stateless, tamper-evident auth tokens.

A token is `base64url(payload) . base64url(hmac_sha256(secret, body))`, where
the payload is a compact JSON object `{"uid": int, "role": str, "exp": int}`.
The signing secret comes from AUTH_SIGNING_SECRET; both minting and verifying
fail closed (raise TokenError) when it is absent, so a misconfigured server
denies rather than trusting unsigned input. Mirrors the HMAC + compare_digest
approach already used for Twilio signature verification.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time


class TokenError(Exception):
    """Raised when a token cannot be minted or fails verification."""


def _secret() -> bytes:
    secret = os.getenv("AUTH_SIGNING_SECRET")
    if not secret:
        raise TokenError("AUTH_SIGNING_SECRET is not configured")
    return secret.encode("utf-8")


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, TypeError) as exc:
        raise TokenError("malformed token encoding") from exc


def _sign(body: str) -> str:
    digest = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def mint_token(
    *,
    user_id: int,
    role: str,
    ttl_seconds: int = 3600,
    now: float | None = None,
) -> str:
    now = time.time() if now is None else now
    payload = {"uid": user_id, "role": role, "exp": int(now + ttl_seconds)}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = _b64encode(raw)
    return f"{body}.{_sign(body)}"


def verify_token(token: str, *, now: float | None = None) -> tuple[int, str]:
    now = time.time() if now is None else now
    try:
        body, signature = token.split(".")
    except ValueError as exc:
        raise TokenError("token must have exactly one '.' separator") from exc

    expected = _sign(body)
    if not hmac.compare_digest(expected, signature):
        raise TokenError("bad signature")

    try:
        payload = json.loads(_b64decode(body))
        user_id = int(payload["uid"])
        role = str(payload["role"])
        exp = int(payload["exp"])
    except (ValueError, TypeError, KeyError) as exc:
        raise TokenError("malformed token payload") from exc

    if exp < now:
        raise TokenError("token expired")

    return user_id, role
