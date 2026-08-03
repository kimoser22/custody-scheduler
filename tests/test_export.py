"""Authenticated family JSON export (archive of durable custody records)."""

from collections.abc import Callable
from datetime import date, datetime

from fastapi.testclient import TestClient
from sqlmodel import Session

from api.dependencies import get_current_user
from core.export import build_family_export
from core.models import OverrideStatus, OverrideType, ParentRole
from database.schema import (
    AuditLogTable,
    BaselineTable,
    OverrideTable,
    SmsOptOutTable,
    UserTable,
)
from main import app


def _override_current_user(user: UserTable) -> Callable[[], UserTable]:
    async def override() -> UserTable:
        return user

    return override


def _seed_family(session: Session) -> tuple[UserTable, UserTable, UserTable]:
    baseline = BaselineTable(
        family_id=1,
        epoch_start_date=date(2026, 1, 1),
        starting_parent=ParentRole.PARENT_A.value,
    )
    parent_a = UserTable(
        id=101,
        family_id=1,
        role="Parent",
        phone="+15550001",
        custody_label="Parent A",
        email="a@example.com",
        passcode_hash="secret-hash-must-not-export",
        calendar_feed_token="feed-token-must-not-export",
    )
    parent_b = UserTable(
        id=102,
        family_id=1,
        role="Parent",
        phone="+15550002",
        custody_label="Parent B",
        email="b@example.com",
        passcode_hash="other-secret",
        calendar_feed_token="other-feed-token",
    )
    viewer = UserTable(
        id=2,
        family_id=1,
        role="Viewer",
        phone=None,
        custody_label=None,
        email=None,
        passcode_hash="viewer-secret",
    )
    override = OverrideTable(
        family_id=1,
        override_date=date(2026, 9, 12),
        end_date=date(2026, 9, 14),
        assigned_parent=ParentRole.PARENT_B.value,
        override_type=OverrideType.HOLIDAY.value,
        description="Spring break",
        is_active=True,
        status=OverrideStatus.APPROVED.value,
        requested_by_user_id=101,
        decided_by_user_id=102,
        decided_at=datetime(2026, 8, 1, 12, 0, 0),
        expires_at=datetime(2026, 8, 8, 12, 0, 0),
    )
    audit = AuditLogTable(
        timestamp=datetime(2026, 8, 1, 12, 0, 0),
        family_id=1,
        actor_role="Parent",
        action_type="override_approved",
        description="Approved holiday",
        previous_state_id=None,
    )
    opt_out = SmsOptOutTable(
        phone="+15550001",
        opted_out_at=datetime(2026, 7, 1, 0, 0, 0),
    )
    stranger_opt_out = SmsOptOutTable(
        phone="+19999999999",
        opted_out_at=datetime(2026, 7, 2, 0, 0, 0),
    )
    session.add(baseline)
    session.add(parent_a)
    session.add(parent_b)
    session.add(viewer)
    session.add(override)
    session.add(audit)
    session.add(opt_out)
    session.add(stranger_opt_out)
    session.commit()
    session.refresh(parent_a)
    session.refresh(parent_b)
    session.refresh(viewer)
    return parent_a, parent_b, viewer


def test_build_family_export_omits_secrets(session_fixture: Session) -> None:
    _seed_family(session_fixture)
    payload = build_family_export(session_fixture, family_id=1)

    assert payload["schema_version"] == 1
    assert payload["family_name"] == "Test Family"
    assert payload["baseline"]["epoch_start_date"] == "2026-01-01"
    assert len(payload["users"]) == 3
    assert len(payload["overrides"]) == 1
    assert payload["overrides"][0]["end_date"] == "2026-09-14"
    assert len(payload["audit_logs"]) == 1
    assert payload["sms_opt_outs"] == [
        {"phone": "+15550001", "opted_out_at": "2026-07-01T00:00:00"}
    ]
    dumped = str(payload)
    assert "passcode_hash" not in dumped
    assert "calendar_feed_token" not in dumped
    assert "secret-hash" not in dumped
    assert "feed-token" not in dumped


def test_export_endpoint_requires_auth(client_fixture: TestClient) -> None:
    response = client_fixture.get("/api/v1/schedule/export.json")
    assert response.status_code == 401


def test_parent_can_download_export(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    parent_a, _, _ = _seed_family(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(parent_a)

    response = client_fixture.get("/api/v1/schedule/export.json")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert 'attachment; filename="custody-export-' in response.headers["content-disposition"]
    assert response.headers["content-disposition"].endswith('.json"')
    body = response.json()
    assert body["schema_version"] == 1
    assert body["family_id"] == 1
    assert len(body["overrides"]) == 1
    assert "passcode_hash" not in response.text
    assert "calendar_feed_token" not in response.text


def test_viewer_can_download_export(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    _, _, viewer = _seed_family(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(viewer)

    response = client_fixture.get("/api/v1/schedule/export.json")

    assert response.status_code == 200
    assert response.json()["family_name"] == "Test Family"


def test_export_unknown_user_404(
    client_fixture: TestClient,
    mock_parent: UserTable,
) -> None:
    # mock_parent id=1 is not inserted into the DB
    app.dependency_overrides[get_current_user] = _override_current_user(mock_parent)

    response = client_fixture.get("/api/v1/schedule/export.json")

    assert response.status_code == 404
