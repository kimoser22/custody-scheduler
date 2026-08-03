"""Failed-login throttling for the public token endpoint.

`POST /api/v1/auth/token` is reachable by anyone and guards custody data, so
repeated wrong passcodes must stop being free. Lockout is keyed by user id and
deliberately short: a stranger spamming wrong passcodes can briefly lock a
parent out, but gains nothing by it and the lock clears itself.

State is per-process, which suits this app (one machine, one uvicorn process —
see the deploy notes in the README). A restart clears the counters; that
slightly favors an attacker who cannot trigger restarts anyway, and is the
right trade against adding a table on the hot path of every login.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

MAX_CONSECUTIVE_FAILURES = 5
LOCKOUT_WINDOW = timedelta(minutes=2)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class LoginThrottle:
    """Counts consecutive failures per user id and locks briefly at the limit."""

    def __init__(self) -> None:
        self._failures: dict[int, int] = {}
        self._locked_until: dict[int, datetime] = {}
        self._lock = threading.Lock()

    def locked_until(self, user_id: int, *, now: datetime | None = None) -> datetime | None:
        """When the lock lifts, or None when the id may attempt a login."""
        moment = now or _utcnow()
        with self._lock:
            until = self._locked_until.get(user_id)
            if until is None:
                return None
            if moment >= until:
                # Expired: clear it so the next failure starts a fresh count.
                self._locked_until.pop(user_id, None)
                self._failures.pop(user_id, None)
                return None
            return until

    def record_failure(self, user_id: int, *, now: datetime | None = None) -> None:
        moment = now or _utcnow()
        with self._lock:
            count = self._failures.get(user_id, 0) + 1
            self._failures[user_id] = count
            if count >= MAX_CONSECUTIVE_FAILURES:
                self._locked_until[user_id] = moment + LOCKOUT_WINDOW

    def record_success(self, user_id: int) -> None:
        with self._lock:
            self._failures.pop(user_id, None)
            self._locked_until.pop(user_id, None)

    def reset(self) -> None:
        """Clear all state (tests)."""
        with self._lock:
            self._failures.clear()
            self._locked_until.clear()


# Shared across requests in this process.
login_throttle = LoginThrottle()
