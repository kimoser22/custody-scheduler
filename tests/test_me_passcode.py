"""PATCH /api/v1/me/passcode — self-service credential rotation."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlmodel import Session

from api.dependencies import get_current_user
from api.login_throttle import MAX_CONSECUTIVE_FAILURES
from api.passcodes import hash_passcode, verify_passcode
from database.schema import UserTable
from main import app


def _override_current_user(user: UserTable) -> Callable[[], UserTable]:
    async def override() -> UserTable:
        return user

    return override


def _seed_parent_with_passcode(
    session: Session,
    *,
    passcode: str = "old-pass",
) -> UserTable:
    parent = UserTable(
        id=101,
        family_id=1,
        role="Parent",
        phone="+15550001",
        custody_label="Parent A",
        email="a@example.com",
        passcode_hash=hash_passcode(passcode),
    )
    session.add(parent)
    session.commit()
    session.refresh(parent)
    return parent


def test_change_passcode_updates_hash_and_login(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    parent = _seed_parent_with_passcode(session_fixture, passcode="old-pass")
    app.dependency_overrides[get_current_user] = _override_current_user(parent)

    response = client_fixture.patch(
        "/api/v1/me/passcode",
        json={"current_passcode": "old-pass", "new_passcode": "new-pass"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}

    session_fixture.refresh(parent)
    assert verify_passcode("new-pass", parent.passcode_hash)
    assert not verify_passcode("old-pass", parent.passcode_hash)

    assert (
        client_fixture.post(
            "/api/v1/auth/token",
            json={"user_id": 101, "passcode": "old-pass"},
        ).status_code
        == 401
    )
    assert (
        client_fixture.post(
            "/api/v1/auth/token",
            json={"user_id": 101, "passcode": "new-pass"},
        ).status_code
        == 200
    )


def test_wrong_current_passcode_is_unauthorized(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    parent = _seed_parent_with_passcode(session_fixture, passcode="old-pass")
    app.dependency_overrides[get_current_user] = _override_current_user(parent)
    before = parent.passcode_hash

    response = client_fixture.patch(
        "/api/v1/me/passcode",
        json={"current_passcode": "wrong", "new_passcode": "new-pass"},
    )

    assert response.status_code == 401
    session_fixture.refresh(parent)
    assert parent.passcode_hash == before


def test_too_short_new_passcode_is_rejected(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    parent = _seed_parent_with_passcode(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(parent)

    response = client_fixture.patch(
        "/api/v1/me/passcode",
        json={"current_passcode": "old-pass", "new_passcode": "abc"},
    )

    assert response.status_code == 400


def test_seven_character_passcode_is_rejected(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    """The token endpoint is public and guards custody data, so the floor has
    to be high enough that guessing is infeasible rather than merely slow."""
    parent = _seed_parent_with_passcode(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(parent)

    response = client_fixture.patch(
        "/api/v1/me/passcode",
        json={"current_passcode": "old-pass", "new_passcode": "abcdefg"},
    )

    assert response.status_code == 400
    session_fixture.refresh(parent)
    assert verify_passcode("old-pass", parent.passcode_hash)


def test_eight_character_passcode_is_accepted(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    parent = _seed_parent_with_passcode(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(parent)

    response = client_fixture.patch(
        "/api/v1/me/passcode",
        json={"current_passcode": "old-pass", "new_passcode": "abcdefgh"},
    )

    assert response.status_code == 200


def test_change_passcode_unauthenticated(client_fixture: TestClient) -> None:
    response = client_fixture.patch(
        "/api/v1/me/passcode",
        json={"current_passcode": "old", "new_passcode": "new-pass"},
    )
    assert response.status_code == 401


def test_null_passcode_hash_cannot_change(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    parent = UserTable(
        id=101,
        family_id=1,
        role="Parent",
        phone="+15550001",
        custody_label="Parent A",
        passcode_hash=None,
    )
    session_fixture.add(parent)
    session_fixture.commit()
    session_fixture.refresh(parent)
    app.dependency_overrides[get_current_user] = _override_current_user(parent)

    response = client_fixture.patch(
        "/api/v1/me/passcode",
        json={"current_passcode": "anything", "new_passcode": "new-pass"},
    )

    assert response.status_code == 400


# --- throttling ---------------------------------------------------------------
#
# This endpoint verifies the current passcode online, exactly like the login
# endpoint, so it is a second guessing surface. Left unthrottled it is the
# *better* one to attack: someone holding a stolen session could grind the
# passcode here without ever tripping the login lock. Both share one counter
# per user, because both are guesses at the same secret.


def _change(client: TestClient, current: str, new: str = "new-passcode"):
    return client.patch(
        "/api/v1/me/passcode",
        json={"current_passcode": current, "new_passcode": new},
    )


def _login(client: TestClient, passcode: str, user_id: int = 101):
    return client.post(
        "/api/v1/auth/token", json={"user_id": user_id, "passcode": passcode}
    )


def test_repeated_wrong_current_passcodes_start_returning_429(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    parent = _seed_parent_with_passcode(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(parent)

    for _ in range(MAX_CONSECUTIVE_FAILURES):
        assert _change(client_fixture, "wrong").status_code == 401

    response = _change(client_fixture, "wrong")
    assert response.status_code == 429
    assert response.headers.get("Retry-After")


def test_lockout_rejects_even_the_correct_current_passcode(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    """Checking the lock only after verifying would let a correct guess on the
    next attempt walk straight through — that is a filter, not a lock."""
    parent = _seed_parent_with_passcode(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(parent)
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        _change(client_fixture, "wrong")

    assert _change(client_fixture, "old-pass").status_code == 429

    session_fixture.refresh(parent)
    assert verify_passcode("old-pass", parent.passcode_hash)


def test_passcode_change_failures_lock_the_login_endpoint(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    parent = _seed_parent_with_passcode(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(parent)
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        _change(client_fixture, "wrong")

    assert _login(client_fixture, "old-pass").status_code == 429


def test_login_failures_lock_the_passcode_change_endpoint(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    parent = _seed_parent_with_passcode(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(parent)
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        _login(client_fixture, "wrong")

    assert _change(client_fixture, "old-pass").status_code == 429


def test_successful_change_clears_the_failure_count(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    parent = _seed_parent_with_passcode(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(parent)
    for _ in range(MAX_CONSECUTIVE_FAILURES - 1):
        _change(client_fixture, "wrong")

    assert _change(client_fixture, "old-pass").status_code == 200

    # Counter reset, so the next wrong attempt is a 401 rather than a lockout.
    assert _change(client_fixture, "wrong").status_code == 401


def test_new_passcode_validation_errors_are_not_counted_as_failures(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    """The current passcode is right every time here — the user is fumbling the
    field they are trying to set. Counting these would let someone lock
    themselves out of their own account while changing it."""
    parent = _seed_parent_with_passcode(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(parent)

    for _ in range(MAX_CONSECUTIVE_FAILURES):
        assert _change(client_fixture, "old-pass", "abc").status_code == 400

    assert _change(client_fixture, "old-pass", "new-passcode").status_code == 200
