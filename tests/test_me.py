"""Parent self-service contact settings: GET/PATCH /api/v1/me."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlmodel import Session

from api.auth_tokens import mint_token
from api.dependencies import get_current_user
from concierge.adapters import SqlSenderResolver
from database.schema import UserTable
from main import app


def _auth_header(user_id: int, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {mint_token(user_id=user_id, role=role)}"}


def _override_current_user(user: UserTable) -> Callable[[], UserTable]:
    async def override() -> UserTable:
        return user

    return override


def _seed_parents(session: Session) -> tuple[UserTable, UserTable]:
    parent_a = UserTable(
        id=101,
        family_id=1,
        role="Parent",
        phone="+15550001",
        custody_label="Parent A",
        email="a@example.com",
    )
    parent_b = UserTable(
        id=102,
        family_id=1,
        role="Parent",
        phone="+15550002",
        custody_label="Parent B",
        email="b@example.com",
    )
    viewer = UserTable(
        id=2,
        family_id=1,
        role="Viewer",
        phone=None,
        custody_label=None,
        email=None,
    )
    session.add(parent_a)
    session.add(parent_b)
    session.add(viewer)
    session.commit()
    session.refresh(parent_a)
    session.refresh(parent_b)
    return parent_a, parent_b


def test_get_me_as_parent_returns_contact_fields(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    parent_a, _ = _seed_parents(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(parent_a)

    response = client_fixture.get("/api/v1/me")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "id": 101,
        "role": "Parent",
        "custody_label": "Parent A",
        "phone": "+15550001",
        "email": "a@example.com",
    }
    assert "passcode_hash" not in body


def test_get_me_unauthenticated(client_fixture: TestClient) -> None:
    response = client_fixture.get("/api/v1/me")
    assert response.status_code == 401


def test_patch_me_updates_own_phone_and_email(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    parent_a, _ = _seed_parents(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(parent_a)

    response = client_fixture.patch(
        "/api/v1/me",
        json={"phone": "1-555-9999", "email": "new-a@example.com"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["phone"] == "+15559999"
    assert body["email"] == "new-a@example.com"

    get_body = client_fixture.get("/api/v1/me").json()
    assert get_body["phone"] == "+15559999"
    assert get_body["email"] == "new-a@example.com"

    resolved = SqlSenderResolver(session_fixture).resolve("+15559999")
    assert resolved is not None
    assert resolved.user_id == 101


def test_patch_me_viewer_forbidden(
    client_fixture: TestClient,
    session_fixture: Session,
    mock_viewer: UserTable,
) -> None:
    _seed_parents(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(mock_viewer)

    response = client_fixture.patch(
        "/api/v1/me",
        json={"email": "viewer@example.com"},
    )
    assert response.status_code == 403


def test_patch_me_does_not_change_other_parent(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    parent_a, parent_b = _seed_parents(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(parent_a)

    client_fixture.patch(
        "/api/v1/me",
        json={"phone": "+15551111", "email": "only-a@example.com"},
    )

    session_fixture.refresh(parent_b)
    assert parent_b.phone == "+15550002"
    assert parent_b.email == "b@example.com"


def test_patch_me_duplicate_phone_conflict(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    parent_a, _ = _seed_parents(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(parent_a)

    response = client_fixture.patch(
        "/api/v1/me",
        json={"phone": "+15550002"},
    )
    assert response.status_code == 409


def test_patch_me_invalid_email(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    parent_a, _ = _seed_parents(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(parent_a)

    response = client_fixture.patch(
        "/api/v1/me",
        json={"email": "not-an-email"},
    )
    assert response.status_code == 400


def test_patch_me_can_clear_email(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    parent_a, _ = _seed_parents(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(parent_a)

    response = client_fixture.patch("/api/v1/me", json={"email": None})
    assert response.status_code == 200
    assert response.json()["email"] is None


def test_patch_me_rejects_empty_phone(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    parent_a, _ = _seed_parents(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(parent_a)

    response = client_fixture.patch("/api/v1/me", json={"phone": "   "})
    assert response.status_code == 400


def test_get_me_with_minted_token(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    _seed_parents(session_fixture)

    response = client_fixture.get(
        "/api/v1/me",
        headers=_auth_header(user_id=101, role="Parent"),
    )
    assert response.status_code == 200
    assert response.json()["id"] == 101
