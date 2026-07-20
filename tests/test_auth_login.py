"""POST /api/v1/auth/token exchanges a passcode for a signed token."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from api.auth_tokens import verify_token
from api.passcodes import hash_passcode
from database.schema import UserTable


@pytest.fixture(name="seed_login_users")
def _seed_login_users(session_fixture: Session) -> None:
    session_fixture.add(
        UserTable(
            id=101,
            family_id=1,
            role="Parent",
            phone="+15550001",
            custody_label="Parent A",
            passcode_hash=hash_passcode("alpha-pass"),
        )
    )
    session_fixture.add(
        UserTable(
            id=2,
            family_id=1,
            role="Viewer",
            passcode_hash=None,  # no credential set — login must be denied
        )
    )
    session_fixture.commit()


def test_valid_passcode_returns_verifiable_token(
    client_fixture: TestClient, seed_login_users: None
) -> None:
    response = client_fixture.post(
        "/api/v1/auth/token",
        json={"user_id": 101, "passcode": "alpha-pass"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == 101
    assert body["role"] == "Parent"
    assert body["token_type"] == "bearer"
    assert verify_token(body["access_token"]) == (101, "Parent")


def test_wrong_passcode_is_unauthorized(
    client_fixture: TestClient, seed_login_users: None
) -> None:
    response = client_fixture.post(
        "/api/v1/auth/token",
        json={"user_id": 101, "passcode": "wrong"},
    )
    assert response.status_code == 401


def test_unknown_user_is_unauthorized(
    client_fixture: TestClient, seed_login_users: None
) -> None:
    response = client_fixture.post(
        "/api/v1/auth/token",
        json={"user_id": 9999, "passcode": "alpha-pass"},
    )
    assert response.status_code == 401


def test_user_without_passcode_cannot_login(
    client_fixture: TestClient, seed_login_users: None
) -> None:
    response = client_fixture.post(
        "/api/v1/auth/token",
        json={"user_id": 2, "passcode": "anything"},
    )
    assert response.status_code == 401


def test_issued_token_authorizes_a_real_request(
    client_fixture: TestClient, seed_login_users: None
) -> None:
    """End-to-end: log in, then use the token on a parent-only route."""
    login = client_fixture.post(
        "/api/v1/auth/token",
        json={"user_id": 101, "passcode": "alpha-pass"},
    )
    token = login.json()["access_token"]
    response = client_fixture.post(
        "/api/v1/schedule/overrides",
        json={
            "override_date": "2026-01-15",
            "assigned_parent": "Parent A",
            "override_type": "Holiday",
            "description": "e2e",
            "is_active": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
