from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from api.auth_tokens import mint_token
from api.dependencies import get_current_user
from core.models import OverrideType, ParentRole, ScheduleOverride
from database.schema import OverrideTable, UserTable
from main import app


def _auth_header(user_id: int, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {mint_token(user_id=user_id, role=role)}"}

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


def _decide(
    client: TestClient, override_id: int, approve: bool
):
    return client.post(
        f"/api/v1/schedule/overrides/{override_id}/decision",
        json={"approve": approve},
    )


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


def test_parent_can_request_override(
    client_fixture: TestClient,
    mock_parent: UserTable,
) -> None:
    app.dependency_overrides[get_current_user] = _override_current_user(mock_parent)

    response = client_fixture.post("/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Pending"
    assert body["is_active"] is False
    assert body["id"] is not None


def test_override_request_ignores_client_supplied_active_and_status(
    client_fixture: TestClient,
    mock_parent: UserTable,
) -> None:
    app.dependency_overrides[get_current_user] = _override_current_user(mock_parent)

    payload = {**OVERRIDE_PAYLOAD, "is_active": True, "status": "Approved"}
    response = client_fixture.post("/api/v1/schedule/overrides", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Pending"
    assert body["is_active"] is False


def test_pending_override_does_not_appear_on_schedule(
    client_fixture: TestClient,
    mock_parent: UserTable,
) -> None:
    app.dependency_overrides[get_current_user] = _override_current_user(mock_parent)

    client_fixture.post("/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD)

    schedule_response = client_fixture.get(
        "/api/v1/schedule/?start_date=2026-01-01&end_date=2026-01-31"
    )
    overridden_day = next(
        day
        for day in schedule_response.json()
        if day["current_date"] == OVERRIDE_PAYLOAD["override_date"]
    )
    assert overridden_day["is_overridden"] is False


def test_other_parent_can_approve_override(
    client_fixture: TestClient,
    mock_parent: UserTable,
    mock_other_parent: UserTable,
) -> None:
    app.dependency_overrides[get_current_user] = _override_current_user(mock_parent)
    create_response = client_fixture.post(
        "/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD
    )
    override_id = create_response.json()["id"]

    app.dependency_overrides[get_current_user] = _override_current_user(mock_other_parent)
    decision_response = _decide(client_fixture, override_id, approve=True)

    assert decision_response.status_code == 200
    assert decision_response.json()["status"] == "Approved"
    assert decision_response.json()["is_active"] is True

    schedule_response = client_fixture.get(
        "/api/v1/schedule/?start_date=2026-01-01&end_date=2026-01-31"
    )
    overridden_day = next(
        day
        for day in schedule_response.json()
        if day["current_date"] == OVERRIDE_PAYLOAD["override_date"]
    )
    assert overridden_day["is_overridden"] is True
    assert overridden_day["final_parent"] == OVERRIDE_PAYLOAD["assigned_parent"]


def test_other_parent_can_reject_override(
    client_fixture: TestClient,
    mock_parent: UserTable,
    mock_other_parent: UserTable,
) -> None:
    app.dependency_overrides[get_current_user] = _override_current_user(mock_parent)
    create_response = client_fixture.post(
        "/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD
    )
    override_id = create_response.json()["id"]

    app.dependency_overrides[get_current_user] = _override_current_user(mock_other_parent)
    decision_response = _decide(client_fixture, override_id, approve=False)

    assert decision_response.status_code == 200
    assert decision_response.json()["status"] == "Rejected"
    assert decision_response.json()["is_active"] is False

    schedule_response = client_fixture.get(
        "/api/v1/schedule/?start_date=2026-01-01&end_date=2026-01-31"
    )
    overridden_day = next(
        day
        for day in schedule_response.json()
        if day["current_date"] == OVERRIDE_PAYLOAD["override_date"]
    )
    assert overridden_day["is_overridden"] is False


def test_requester_cannot_approve_own_override(
    client_fixture: TestClient,
    mock_parent: UserTable,
) -> None:
    app.dependency_overrides[get_current_user] = _override_current_user(mock_parent)
    create_response = client_fixture.post(
        "/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD
    )
    override_id = create_response.json()["id"]

    decision_response = _decide(client_fixture, override_id, approve=True)

    assert decision_response.status_code == 403


def test_viewer_cannot_decide_override(
    client_fixture: TestClient,
    mock_parent: UserTable,
    mock_viewer: UserTable,
) -> None:
    app.dependency_overrides[get_current_user] = _override_current_user(mock_parent)
    create_response = client_fixture.post(
        "/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD
    )
    override_id = create_response.json()["id"]

    app.dependency_overrides[get_current_user] = _override_current_user(mock_viewer)
    decision_response = _decide(client_fixture, override_id, approve=True)

    assert decision_response.status_code == 403


def test_deciding_an_already_decided_override_conflicts(
    client_fixture: TestClient,
    mock_parent: UserTable,
    mock_other_parent: UserTable,
) -> None:
    app.dependency_overrides[get_current_user] = _override_current_user(mock_parent)
    create_response = client_fixture.post(
        "/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD
    )
    override_id = create_response.json()["id"]

    app.dependency_overrides[get_current_user] = _override_current_user(mock_other_parent)
    first = _decide(client_fixture, override_id, approve=True)
    assert first.status_code == 200

    second = _decide(client_fixture, override_id, approve=True)
    assert second.status_code == 409


def test_deciding_an_expired_override_returns_410(
    client_fixture: TestClient,
    session_fixture: Session,
    mock_other_parent: UserTable,
) -> None:
    expired_row = OverrideTable(
        family_id=1,
        override_date=datetime(2026, 1, 15).date(),
        assigned_parent=ParentRole.PARENT_A.value,
        override_type=OverrideType.HOLIDAY.value,
        description="Already expired request",
        is_active=False,
        status="Pending",
        requested_by_user_id=1,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1),
    )
    session_fixture.add(expired_row)
    session_fixture.commit()
    session_fixture.refresh(expired_row)

    app.dependency_overrides[get_current_user] = _override_current_user(mock_other_parent)
    response = _decide(client_fixture, expired_row.id, approve=True)

    assert response.status_code == 410


def test_replacing_approved_override_on_same_date_supersedes_previous(
    client_fixture: TestClient,
    mock_parent: UserTable,
    mock_other_parent: UserTable,
) -> None:
    app.dependency_overrides[get_current_user] = _override_current_user(mock_parent)
    first_request = client_fixture.post(
        "/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD
    )
    first_id = first_request.json()["id"]

    app.dependency_overrides[get_current_user] = _override_current_user(mock_other_parent)
    _decide(client_fixture, first_id, approve=True)

    app.dependency_overrides[get_current_user] = _override_current_user(mock_parent)
    second_payload = {
        **OVERRIDE_PAYLOAD,
        "assigned_parent": ParentRole.PARENT_B.value,
        "description": "Replacement request",
    }
    second_request = client_fixture.post(
        "/api/v1/schedule/overrides", json=second_payload
    )
    second_id = second_request.json()["id"]

    app.dependency_overrides[get_current_user] = _override_current_user(mock_other_parent)
    second_decision = _decide(client_fixture, second_id, approve=True)
    assert second_decision.status_code == 200

    schedule_response = client_fixture.get(
        "/api/v1/schedule/?start_date=2026-01-01&end_date=2026-01-31"
    )
    overridden_day = next(
        day
        for day in schedule_response.json()
        if day["current_date"] == OVERRIDE_PAYLOAD["override_date"]
    )
    assert overridden_day["final_parent"] == ParentRole.PARENT_B.value
    assert overridden_day["override_details"]["description"] == "Replacement request"


def test_sweep_expired_overrides(
    client_fixture: TestClient,
    session_fixture: Session,
    mock_parent: UserTable,
) -> None:
    expired_row = OverrideTable(
        family_id=1,
        override_date=datetime(2026, 2, 1).date(),
        assigned_parent=ParentRole.PARENT_A.value,
        override_type=OverrideType.HOLIDAY.value,
        description="Stale request nobody answered",
        is_active=False,
        status="Pending",
        requested_by_user_id=1,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1),
    )
    session_fixture.add(expired_row)
    session_fixture.commit()

    app.dependency_overrides[get_current_user] = _override_current_user(mock_parent)
    response = client_fixture.post("/api/v1/schedule/overrides/sweep-expired")

    assert response.status_code == 200
    assert response.json()["expired_count"] == 1


def test_pending_overrides_listing_returns_pending_for_family(
    client_fixture: TestClient,
    mock_parent: UserTable,
) -> None:
    app.dependency_overrides[get_current_user] = _override_current_user(mock_parent)
    client_fixture.post("/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD)

    response = client_fixture.get("/api/v1/schedule/overrides/pending")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "Pending"
    assert body[0]["requested_by_user_id"] == mock_parent.id


def test_pending_overrides_listing_excludes_decided_requests(
    client_fixture: TestClient,
    mock_parent: UserTable,
    mock_other_parent: UserTable,
) -> None:
    app.dependency_overrides[get_current_user] = _override_current_user(mock_parent)
    create_response = client_fixture.post(
        "/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD
    )
    override_id = create_response.json()["id"]

    app.dependency_overrides[get_current_user] = _override_current_user(mock_other_parent)
    _decide(client_fixture, override_id, approve=True)

    response = client_fixture.get("/api/v1/schedule/overrides/pending")

    assert response.status_code == 200
    assert response.json() == []


def test_forged_prefix_token_is_rejected(client_fixture: TestClient) -> None:
    """The old fabricated `parent:a` form is no longer a valid credential — it
    carries no signature, so it must be rejected rather than granting parent
    rights to anyone who sends the string."""
    response = client_fixture.post(
        "/api/v1/schedule/overrides",
        json=OVERRIDE_PAYLOAD,
        headers={"Authorization": "parent:a"},
    )
    assert response.status_code == 401


def test_token_signed_with_wrong_secret_is_rejected(
    client_fixture: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUTH_SIGNING_SECRET", "attacker-secret")
    forged = f"Bearer {mint_token(user_id=101, role='Parent')}"
    monkeypatch.setenv("AUTH_SIGNING_SECRET", "test-signing-secret")
    response = client_fixture.post(
        "/api/v1/schedule/overrides",
        json=OVERRIDE_PAYLOAD,
        headers={"Authorization": forged},
    )
    assert response.status_code == 401


def test_minted_parent_token_grants_parent_access(
    client_fixture: TestClient,
) -> None:
    response = client_fixture.post(
        "/api/v1/schedule/overrides",
        json=OVERRIDE_PAYLOAD,
        headers=_auth_header(user_id=101, role="Parent"),
    )
    assert response.status_code == 200


def test_minted_viewer_token_cannot_create_override(
    client_fixture: TestClient,
) -> None:
    response = client_fixture.post(
        "/api/v1/schedule/overrides",
        json=OVERRIDE_PAYLOAD,
        headers=_auth_header(user_id=2, role="Viewer"),
    )
    assert response.status_code == 403


def test_distinct_parent_tokens_have_stable_but_different_identities(
    client_fixture: TestClient,
) -> None:
    create_response = client_fixture.post(
        "/api/v1/schedule/overrides",
        json=OVERRIDE_PAYLOAD,
        headers=_auth_header(user_id=101, role="Parent"),
    )
    assert create_response.status_code == 200
    override_id = create_response.json()["id"]

    self_decision = client_fixture.post(
        f"/api/v1/schedule/overrides/{override_id}/decision",
        json={"approve": True},
        headers=_auth_header(user_id=101, role="Parent"),
    )
    assert self_decision.status_code == 403

    other_decision = client_fixture.post(
        f"/api/v1/schedule/overrides/{override_id}/decision",
        json={"approve": True},
        headers=_auth_header(user_id=102, role="Parent"),
    )
    assert other_decision.status_code == 200
    assert other_decision.json()["status"] == "Approved"
