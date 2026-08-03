"""PATCH /api/v1/me/passcode — self-service credential rotation."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlmodel import Session

from api.dependencies import get_current_user
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
