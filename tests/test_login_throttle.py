"""Failed-login throttling for POST /api/v1/auth/token.

The endpoint is public and guards custody data, so repeated wrong passcodes
must stop being free. Lockout is per user id and short-lived: a stranger can
briefly lock a parent out, but gains nothing by it and it self-heals.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from api.login_throttle import (
    LOCKOUT_WINDOW,
    MAX_CONSECUTIVE_FAILURES,
    LoginThrottle,
)
from api.passcodes import hash_passcode
from database.schema import UserTable

PASSCODE = "river-otter-42"
START = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)


@pytest.fixture(name="parent")
def _parent(session_fixture: Session) -> UserTable:
    user = UserTable(
        id=101,
        family_id=1,
        role="Parent",
        custody_label="Parent A",
        passcode_hash=hash_passcode(PASSCODE),
    )
    session_fixture.add(user)
    session_fixture.commit()
    return user


def _login(client: TestClient, passcode: str, user_id: int = 101):
    return client.post(
        "/api/v1/auth/token", json={"user_id": user_id, "passcode": passcode}
    )


# --- the throttle itself (pure, clock injected) -------------------------------


def test_allows_attempts_below_the_threshold() -> None:
    throttle = LoginThrottle()
    for _ in range(MAX_CONSECUTIVE_FAILURES - 1):
        throttle.record_failure(101, now=START)
    assert throttle.locked_until(101, now=START) is None


def test_locks_after_consecutive_failures() -> None:
    throttle = LoginThrottle()
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        throttle.record_failure(101, now=START)
    assert throttle.locked_until(101, now=START) == START + LOCKOUT_WINDOW


def test_lock_expires_after_the_window() -> None:
    throttle = LoginThrottle()
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        throttle.record_failure(101, now=START)

    later = START + LOCKOUT_WINDOW + timedelta(seconds=1)
    assert throttle.locked_until(101, now=later) is None


def test_success_resets_the_counter() -> None:
    throttle = LoginThrottle()
    for _ in range(MAX_CONSECUTIVE_FAILURES - 1):
        throttle.record_failure(101, now=START)
    throttle.record_success(101)

    throttle.record_failure(101, now=START)
    assert throttle.locked_until(101, now=START) is None


def test_lock_is_per_user() -> None:
    """One parent locking out must never lock the other out of the calendar."""
    throttle = LoginThrottle()
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        throttle.record_failure(101, now=START)

    assert throttle.locked_until(101, now=START) is not None
    assert throttle.locked_until(102, now=START) is None


# --- endpoint behavior --------------------------------------------------------


def test_repeated_wrong_passcodes_start_returning_429(
    client_fixture: TestClient, parent: UserTable
) -> None:
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        assert _login(client_fixture, "wrong").status_code == 401

    response = _login(client_fixture, "wrong")
    assert response.status_code == 429
    assert response.headers.get("Retry-After")


def test_lockout_rejects_even_the_correct_passcode(
    client_fixture: TestClient, parent: UserTable
) -> None:
    """Otherwise the lockout is trivially bypassed by guessing correctly on the
    next attempt — the point is to stop the guessing, not just wrong answers."""
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        _login(client_fixture, "wrong")

    assert _login(client_fixture, PASSCODE).status_code == 429


def test_successful_login_clears_the_failure_count(
    client_fixture: TestClient, parent: UserTable
) -> None:
    for _ in range(MAX_CONSECUTIVE_FAILURES - 1):
        _login(client_fixture, "wrong")
    assert _login(client_fixture, PASSCODE).status_code == 200

    # Counter reset, so the next wrong attempt is a 401 rather than a lockout.
    assert _login(client_fixture, "wrong").status_code == 401


def test_unknown_user_id_is_throttled_without_revealing_it_exists(
    client_fixture: TestClient, parent: UserTable
) -> None:
    """Unknown ids must throttle too, or they become a free oracle — and the
    status must stay 401 until lockout so it matches a wrong passcode."""
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        assert _login(client_fixture, "wrong", user_id=999).status_code == 401

    assert _login(client_fixture, "wrong", user_id=999).status_code == 429
