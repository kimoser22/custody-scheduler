"""What the shared Viewer account may and may not do.

Viewer is ONE account handed to everyone outside the two parents
(grandparents, a sitter). That sharing is what makes these gates matter: a
capability granted to "the Viewer" is granted to everybody holding that
passcode at once, and any of them can exercise it against the others.

Two capabilities were reachable and should not be:
  * changing the passcode -- one holder can lock out every other holder, and
    the parents, with a value nobody else knows.
  * downloading the family record -- both parents' phone numbers and email
    addresses plus the complete custody audit log.

The negative tests below are only half the point; the positive ones guard
against over-gating, because reading the calendar and subscribing to it are
the entire reason the Viewer account exists.
"""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlmodel import Session

from api.dependencies import get_current_user
from api.passcodes import hash_passcode
from database.schema import UserTable
from main import app

VIEWER_PASSCODE = "viewer-pass"
PARENT_PASSCODE = "parent-pass"


def _as(user: UserTable) -> Callable[[], UserTable]:
    async def override() -> UserTable:
        return user

    return override


def _seed(session: Session) -> tuple[UserTable, UserTable]:
    viewer = UserTable(
        id=2, family_id=1, role="Viewer",
        passcode_hash=hash_passcode(VIEWER_PASSCODE),
    )
    parent = UserTable(
        id=101, family_id=1, role="Parent", phone="+15550001",
        custody_label="Parent A", email="a@example.com",
        passcode_hash=hash_passcode(PARENT_PASSCODE),
    )
    session.add(viewer)
    session.add(parent)
    session.commit()
    session.refresh(viewer)
    session.refresh(parent)
    return viewer, parent


# --- must be refused ----------------------------------------------------------


def test_viewer_cannot_download_the_family_record(
    client_fixture: TestClient, session_fixture: Session
) -> None:
    """The export carries both parents' phone numbers, emails and the whole
    audit log. A shared account must not hand that to everyone holding it."""
    viewer, _ = _seed(session_fixture)
    app.dependency_overrides[get_current_user] = _as(viewer)

    response = client_fixture.get("/api/v1/schedule/export.json")

    assert response.status_code == 403


def test_viewer_cannot_change_the_shared_passcode(
    client_fixture: TestClient, session_fixture: Session
) -> None:
    """One holder rotating the shared passcode locks out every other holder."""
    viewer, _ = _seed(session_fixture)
    app.dependency_overrides[get_current_user] = _as(viewer)
    before = viewer.passcode_hash

    response = client_fixture.patch(
        "/api/v1/me/passcode",
        json={"current_passcode": VIEWER_PASSCODE, "new_passcode": "brand-new-pass"},
    )

    assert response.status_code == 403
    session_fixture.refresh(viewer)
    assert viewer.passcode_hash == before  # knowing the current one is not enough


# --- must keep working (guards against over-gating) ---------------------------


def test_viewer_can_still_read_the_schedule(
    client_fixture: TestClient, session_fixture: Session
) -> None:
    """Reading the calendar is the entire point of the Viewer account."""
    viewer, _ = _seed(session_fixture)
    app.dependency_overrides[get_current_user] = _as(viewer)

    response = client_fixture.get(
        "/api/v1/schedule/",
        params={"start_date": "2026-08-10", "end_date": "2026-08-12"},
    )

    assert response.status_code == 200
    assert len(response.json()) == 3


def test_viewer_can_still_subscribe_to_the_calendar_feed(
    client_fixture: TestClient, session_fixture: Session
) -> None:
    """Grandparents subscribing in their own calendar app is the use case."""
    viewer, _ = _seed(session_fixture)
    app.dependency_overrides[get_current_user] = _as(viewer)

    response = client_fixture.post("/api/v1/me/calendar-feed", json={})

    assert response.status_code == 200
    assert response.json()["token"]


def test_parent_can_still_download_the_family_record(
    client_fixture: TestClient, session_fixture: Session
) -> None:
    _, parent = _seed(session_fixture)
    app.dependency_overrides[get_current_user] = _as(parent)

    response = client_fixture.get("/api/v1/schedule/export.json")

    assert response.status_code == 200
    assert "custody-export-" in response.headers["content-disposition"]


def test_parent_can_still_change_their_own_passcode(
    client_fixture: TestClient, session_fixture: Session
) -> None:
    _, parent = _seed(session_fixture)
    app.dependency_overrides[get_current_user] = _as(parent)

    response = client_fixture.patch(
        "/api/v1/me/passcode",
        json={"current_passcode": PARENT_PASSCODE, "new_passcode": "rotated-pass"},
    )

    assert response.status_code == 200
