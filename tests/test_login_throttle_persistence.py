"""The failed-passcode lockout must outlive the process that recorded it.

The throttle used to be a module-level dict. This repo auto-deploys on every
merge to master, so that counter has already been wiped dozens of times — an
attacker mid-guess got a clean slate each time, for free. The load-bearing test
here is the restart proof: it throws away every in-process object and rebuilds
the throttle from the database file alone.

These also cover the lock semantics themselves (clock injected, no HTTP), which
is why they live beside the persistence proof rather than in the endpoint tests.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine

from api.login_throttle import (
    LOCKOUT_WINDOW,
    MAX_CONSECUTIVE_FAILURES,
    SqlLoginThrottle,
)
from database.schema import LoginAttemptTable

START = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)


@pytest.fixture(name="db_url")
def _db_url(tmp_path) -> str:
    """A real on-disk database — durability only means anything for a file."""
    url = f"sqlite:///{tmp_path.as_posix()}/throttle.db"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    engine.dispose()
    return url


@pytest.fixture(name="session")
def _session(db_url: str):
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    with Session(engine) as session:
        yield session
    engine.dispose()


def _lock_out(throttle: SqlLoginThrottle, user_id: int, *, now: datetime) -> None:
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        throttle.record_failure(user_id, now=now)


# --- the reason this change exists -------------------------------------------


def test_lock_survives_a_restart(db_url: str) -> None:
    """A deploy in the middle of a guessing run must not hand back a clean slate."""
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    with Session(engine) as session:
        _lock_out(SqlLoginThrottle(session), 101, now=START)
    engine.dispose()

    # Nothing above survives into here: new engine, new session, new throttle.
    restarted = create_engine(db_url, connect_args={"check_same_thread": False})
    with Session(restarted) as session:
        assert (
            SqlLoginThrottle(session).locked_until(101, now=START)
            == START + LOCKOUT_WINDOW
        )
    restarted.dispose()


# --- lock semantics -----------------------------------------------------------


def test_allows_attempts_below_the_threshold(session: Session) -> None:
    throttle = SqlLoginThrottle(session)
    for _ in range(MAX_CONSECUTIVE_FAILURES - 1):
        throttle.record_failure(101, now=START)

    assert throttle.locked_until(101, now=START) is None


def test_locks_after_consecutive_failures(session: Session) -> None:
    throttle = SqlLoginThrottle(session)
    _lock_out(throttle, 101, now=START)

    assert throttle.locked_until(101, now=START) == START + LOCKOUT_WINDOW


def test_lock_expires_after_the_window(session: Session) -> None:
    throttle = SqlLoginThrottle(session)
    _lock_out(throttle, 101, now=START)

    later = START + LOCKOUT_WINDOW + timedelta(seconds=1)
    assert throttle.locked_until(101, now=later) is None


def test_expired_lock_clears_the_row_so_the_count_starts_fresh(
    session: Session,
) -> None:
    """Otherwise a sixth failure long after the window would re-lock instantly,
    turning a two-minute lockout into a permanent one."""
    throttle = SqlLoginThrottle(session)
    _lock_out(throttle, 101, now=START)

    later = START + LOCKOUT_WINDOW + timedelta(seconds=1)
    assert throttle.locked_until(101, now=later) is None
    assert session.get(LoginAttemptTable, 101) is None

    throttle.record_failure(101, now=later)
    assert throttle.locked_until(101, now=later) is None


def test_success_clears_an_existing_lock_and_counter(session: Session) -> None:
    throttle = SqlLoginThrottle(session)
    _lock_out(throttle, 101, now=START)

    throttle.record_success(101)

    assert throttle.locked_until(101, now=START) is None
    assert session.get(LoginAttemptTable, 101) is None


def test_lock_is_per_user(session: Session) -> None:
    """One parent locking out must never lock the other out of the calendar."""
    throttle = SqlLoginThrottle(session)
    _lock_out(throttle, 101, now=START)

    assert throttle.locked_until(101, now=START) is not None
    assert throttle.locked_until(102, now=START) is None
