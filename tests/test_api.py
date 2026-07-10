from collections.abc import Callable

from fastapi.testclient import TestClient

from api.dependencies import get_current_user
from core.models import OverrideType, ParentRole, ScheduleOverride
from database.schema import UserTable
from main import app

OVERRIDE_PAYLOAD = {
    "override_date": "2026-01-15",
    "assigned_parent": ParentRole.PARENT_A.value,
    "override_type": OverrideType.HOLIDAY.value,
    "description": "Test holiday override",
    "is_active": True,
}


def _override_current_user(user: UserTable) -> Callable[[], UserTable]:
    async def override() -> UserTable:
        return user

    return override


def test_unauthenticated_access(client_fixture: TestClient) -> None:
    response = client_fixture.get("/api/v1/schedule/")

    assert response.status_code == 401


def test_viewer_can_read_schedule(
    client_fixture: TestClient,
    mock_viewer: UserTable,
) -> None:
    app.dependency_overrides[get_current_user] = _override_current_user(mock_viewer)

    response = client_fixture.get(
        "/api/v1/schedule/?start_date=2026-01-01&end_date=2026-01-14"
    )

    assert response.status_code == 200


def test_viewer_blocked_from_writing(
    client_fixture: TestClient,
    mock_viewer: UserTable,
) -> None:
    app.dependency_overrides[get_current_user] = _override_current_user(mock_viewer)

    response = client_fixture.post("/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD)

    assert response.status_code == 403
    assert response.json()["detail"] == "Action restricted to Parent roles only."


def test_parent_can_write_override(
    client_fixture: TestClient,
    mock_parent: UserTable,
) -> None:
    app.dependency_overrides[get_current_user] = _override_current_user(mock_parent)

    response = client_fixture.post("/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD)

    assert response.status_code == 200
