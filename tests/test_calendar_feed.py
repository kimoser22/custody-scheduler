"""Calendar feed token mint/rotate and ICS subscribe endpoint."""

from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlmodel import Session

from api.dependencies import get_current_user
from database.schema import BaselineTable, OverrideTable, UserTable
from main import app, ensure_calendar_feed_token_column
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine


def _override_current_user(user: UserTable) -> Callable[[], UserTable]:
    async def override() -> UserTable:
        return user

    return override


def _seed_users(session: Session) -> tuple[UserTable, UserTable]:
    session.add(
        BaselineTable(
            family_id=1,
            epoch_start_date=date(2026, 1, 5),
            starting_parent="Parent A",
        )
    )
    viewer = UserTable(
        id=2,
        family_id=1,
        role="Viewer",
        phone=None,
        custody_label=None,
    )
    parent = UserTable(
        id=101,
        family_id=1,
        role="Parent",
        phone="+15550001",
        custody_label="Parent A",
        email="a@example.com",
    )
    session.add(viewer)
    session.add(parent)
    session.commit()
    session.refresh(viewer)
    session.refresh(parent)
    return viewer, parent


def test_calendar_feed_unknown_token_unauthorized(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    _seed_users(session_fixture)
    response = client_fixture.get(
        "/api/v1/schedule/feed.ics",
        params={"token": "not-a-real-token"},
    )
    assert response.status_code == 401


def test_mint_calendar_feed_as_viewer(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    viewer, _ = _seed_users(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(viewer)

    response = client_fixture.post("/api/v1/me/calendar-feed", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["token"]
    assert body["url"].endswith(f"/api/v1/schedule/feed.ics?token={body['token']}")

    # Second mint without rotate keeps the same token.
    again = client_fixture.post("/api/v1/me/calendar-feed", json={})
    assert again.json()["token"] == body["token"]


def test_calendar_feed_returns_ics_with_required_headers(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    viewer, _ = _seed_users(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(viewer)
    token = client_fixture.post("/api/v1/me/calendar-feed", json={}).json()["token"]

    response = client_fixture.get(
        "/api/v1/schedule/feed.ics",
        params={"token": token},
    )
    assert response.status_code == 200
    assert "text/calendar" in response.headers["content-type"]
    assert 'filename="custody.ics"' in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "private, max-age=300"
    body = response.text
    assert "BEGIN:VCALENDAR" in body
    assert "VERSION:2.0" in body
    assert "BEGIN:VEVENT" in body
    assert "SUMMARY:Custody:" in body


def test_rotate_invalidates_old_token(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    viewer, _ = _seed_users(session_fixture)
    app.dependency_overrides[get_current_user] = _override_current_user(viewer)
    old = client_fixture.post("/api/v1/me/calendar-feed", json={}).json()["token"]
    new = client_fixture.post(
        "/api/v1/me/calendar-feed", json={"rotate": True}
    ).json()["token"]
    assert new != old
    assert (
        client_fixture.get(
            "/api/v1/schedule/feed.ics", params={"token": old}
        ).status_code
        == 401
    )
    assert (
        client_fixture.get(
            "/api/v1/schedule/feed.ics", params={"token": new}
        ).status_code
        == 200
    )


def test_mint_calendar_feed_unauthenticated(client_fixture: TestClient) -> None:
    response = client_fixture.post("/api/v1/me/calendar-feed", json={})
    assert response.status_code == 401


def test_feed_includes_approved_override_description(
    client_fixture: TestClient,
    session_fixture: Session,
) -> None:
    viewer, parent = _seed_users(session_fixture)
    today = datetime.now(timezone.utc).date()
    session_fixture.add(
        OverrideTable(
            family_id=1,
            override_date=today,
            end_date=today,
            assigned_parent="Parent B",
            override_type="Holiday",
            description="Feed override note",
            is_active=True,
            status="Approved",
            requested_by_user_id=parent.id,
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None)
            + timedelta(hours=1),
        )
    )
    session_fixture.commit()

    app.dependency_overrides[get_current_user] = _override_current_user(viewer)
    token = client_fixture.post("/api/v1/me/calendar-feed", json={}).json()["token"]
    body = client_fixture.get(
        "/api/v1/schedule/feed.ics", params={"token": token}
    ).text
    assert "DESCRIPTION:Feed override note" in body
    assert "SUMMARY:Custody: Parent B" in body


def test_calendar_feed_token_migration_idempotent() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                family_id INTEGER NOT NULL,
                role VARCHAR NOT NULL
            )
            """
        )
        conn.commit()
    ensure_calendar_feed_token_column(engine)
    ensure_calendar_feed_token_column(engine)
    with engine.connect() as conn:
        cols = {
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(users)")
        }
    assert "calendar_feed_token" in cols
