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
    days = response.json()
    assert len(days) == 14
    assert days[0]["current_date"] == "2026-01-01"
    assert days[-1]["current_date"] == "2026-01-14"


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


def test_parent_override_persists_on_schedule(
    client_fixture: TestClient,
    mock_parent: UserTable,
) -> None:
    app.dependency_overrides[get_current_user] = _override_current_user(mock_parent)

    create_response = client_fixture.post(
        "/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD
    )
    assert create_response.status_code == 200

    schedule_response = client_fixture.get(
        "/api/v1/schedule/?start_date=2026-01-01&end_date=2026-01-31"
    )
    assert schedule_response.status_code == 200

    overridden_day = next(
        day
        for day in schedule_response.json()
        if day["current_date"] == OVERRIDE_PAYLOAD["override_date"]
    )
    assert overridden_day["is_overridden"] is True
    assert overridden_day["final_parent"] == OVERRIDE_PAYLOAD["assigned_parent"]
    assert (
        overridden_day["override_details"]["description"]
        == OVERRIDE_PAYLOAD["description"]
    )


def test_override_ignores_client_supplied_inactive_flag(
    client_fixture: TestClient,
    mock_parent: UserTable,
) -> None:
    app.dependency_overrides[get_current_user] = _override_current_user(mock_parent)

    payload = {**OVERRIDE_PAYLOAD, "is_active": False}
    create_response = client_fixture.post("/api/v1/schedule/overrides", json=payload)

    assert create_response.status_code == 200
    assert create_response.json()["is_active"] is True

    schedule_response = client_fixture.get(
        "/api/v1/schedule/?start_date=2026-01-01&end_date=2026-01-31"
    )
    overridden_day = next(
        day
        for day in schedule_response.json()
        if day["current_date"] == OVERRIDE_PAYLOAD["override_date"]
    )
    assert overridden_day["is_overridden"] is True


def test_replacing_override_on_same_date_supersedes_previous(
    client_fixture: TestClient,
    mock_parent: UserTable,
) -> None:
    app.dependency_overrides[get_current_user] = _override_current_user(mock_parent)

    client_fixture.post("/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD)

    second_payload = {
        **OVERRIDE_PAYLOAD,
        "assigned_parent": ParentRole.PARENT_B.value,
        "description": "Replacement override",
    }
    second_response = client_fixture.post(
        "/api/v1/schedule/overrides", json=second_payload
    )
    assert second_response.status_code == 200

    schedule_response = client_fixture.get(
        "/api/v1/schedule/?start_date=2026-01-01&end_date=2026-01-31"
    )
    overridden_day = next(
        day
        for day in schedule_response.json()
        if day["current_date"] == OVERRIDE_PAYLOAD["override_date"]
    )
    assert overridden_day["final_parent"] == ParentRole.PARENT_B.value
    assert overridden_day["override_details"]["description"] == "Replacement override"
