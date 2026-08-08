"""Failed-passcode throttling for the endpoints that verify one online.

Two endpoints check a passcode against its hash: `POST /api/v1/auth/token`
(public) and `PATCH /api/v1/me/passcode` (authenticated). Both are guessing
surfaces for the same secret, so both draw on one counter per user id — an
attacker holding a stolen session should not get a fresh budget by moving to the
other endpoint.

Lockout is deliberately short and keyed by user id: a stranger spamming wrong
passcodes can briefly lock a parent out, but gains nothing by it and the lock
clears itself.

State lives in the database rather than in this process. That costs a small
write on failure and buys the only thing that matters here: this app redeploys
on every merge to master, and a process-local counter would reset each time,
mid-guess, for free.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Protocol

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from database.schema import LoginAttemptTable

MAX_CONSECUTIVE_FAILURES = 5
LOCKOUT_WINDOW = timedelta(minutes=2)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class LoginThrottle(Protocol):
    """Counts consecutive failures per user id and locks briefly at the limit."""

    def locked_until(
        self, user_id: int, *, now: datetime | None = None
    ) -> datetime | None:
        """When the lock lifts, or None when the id may attempt a passcode."""
        ...

    def record_failure(self, user_id: int, *, now: datetime | None = None) -> None: ...

    def record_success(self, user_id: int) -> None: ...


class SqlLoginThrottle:
    def __init__(self, session: Session) -> None:
        self._session = session

    def locked_until(
        self, user_id: int, *, now: datetime | None = None
    ) -> datetime | None:
        moment = now or _utcnow()
        row = self._session.get(LoginAttemptTable, user_id)
        if row is None or row.locked_until is None:
            return None
        if moment >= row.locked_until:
            # Expired: drop the row so the next failure starts a fresh count,
            # rather than re-locking on the very next attempt forever.
            self._session.delete(row)
            self._session.commit()
            return None
        return row.locked_until

    def record_failure(self, user_id: int, *, now: datetime | None = None) -> None:
        moment = now or _utcnow()
        row = self._session.get(LoginAttemptTable, user_id)
        if row is None:
            row = LoginAttemptTable(user_id=user_id, failure_count=0)
        row.failure_count += 1
        if row.failure_count >= MAX_CONSECUTIVE_FAILURES:
            row.locked_until = moment + LOCKOUT_WINDOW
        self._session.add(row)
        try:
            self._session.commit()
        except IntegrityError:
            # A concurrent failure inserted the row first. Losing one increment
            # of a five-strike counter is not worth a retry loop.
            self._session.rollback()

    def record_success(self, user_id: int) -> None:
        row = self._session.get(LoginAttemptTable, user_id)
        if row is None:
            return
        self._session.delete(row)
        self._session.commit()


def lockout_error(locked_until: datetime, *, now: datetime) -> HTTPException:
    """The 429 both throttled endpoints raise, so they stay identical."""
    retry_after = max(1, math.ceil((locked_until - now).total_seconds()))
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many failed attempts. Try again shortly.",
        headers={"Retry-After": str(retry_after)},
    )
