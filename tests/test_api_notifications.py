"""Endpoint behavior for notifications, audit history, and expiry filtering.

A notification is a side effect of a custody decision, never a precondition:
these tests pin that a mail failure or a missing address cannot fail the
request or lose the override.
"""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from api.dependencies import get_current_user, get_notifier, get_sms_gateway
from concierge.ports import FakeSmsGateway, OptOutAwareSmsGateway
from concierge.repos import SqlOptOutStore
from core.models import OverrideStatus, OverrideType, ParentRole
from core.notifications import FakeNotifier
from database.schema import AuditLogTable, OverrideTable, UserTable
from main import app

PARENT_A_EMAIL = "parent.a@example.com"
PARENT_B_EMAIL = "parent.b@example.com"
PARENT_A_PHONE = "+15550001"
PARENT_B_PHONE = "+15550002"

OVERRIDE_PAYLOAD = {
    "override_date": "2026-08-07",
    "assigned_parent": ParentRole.PARENT_B.value,
    "override_type": OverrideType.MUTUAL_SWAP.value,
    "description": "soccer tournament",
    "is_active": True,
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _override_current_user(user: UserTable) -> Callable[[], UserTable]:
    async def override() -> UserTable:
        return user

    return override


def _parent(user_id: int, label: str) -> UserTable:
    return UserTable(id=user_id, family_id=1, role="Parent", custody_label=label)


def _seed_parents(
    session: Session,
    *,
    parent_a_email: str | None = PARENT_A_EMAIL,
    parent_b_email: str | None = PARENT_B_EMAIL,
    parent_a_phone: str | None = PARENT_A_PHONE,
    parent_b_phone: str | None = PARENT_B_PHONE,
) -> None:
    session.add(
        UserTable(
            id=101,
            family_id=1,
            role="Parent",
            custody_label="Parent A",
            email=parent_a_email,
            phone=parent_a_phone,
        )
    )
    session.add(
        UserTable(
            id=102,
            family_id=1,
            role="Parent",
            custody_label="Parent B",
            email=parent_b_email,
            phone=parent_b_phone,
        )
    )
    session.commit()


@pytest.fixture(name="notifier")
def _notifier() -> FakeNotifier:
    notifier = FakeNotifier()
    app.dependency_overrides[get_notifier] = lambda: notifier
    return notifier


@pytest.fixture(name="sms")
def _sms(session_fixture: Session) -> FakeSmsGateway:
    """Wrap the fake the way production wraps Twilio, so these tests exercise
    the real opt-out gating rather than a call-site check."""
    inner = FakeSmsGateway()
    gateway = OptOutAwareSmsGateway(inner, SqlOptOutStore(session_fixture))
    app.dependency_overrides[get_sms_gateway] = lambda: gateway
    return inner


def _act_as(user_id: int, label: str) -> None:
    app.dependency_overrides[get_current_user] = _override_current_user(
        _parent(user_id, label)
    )


def _pending_row(session: Session) -> OverrideTable:
    return session.exec(select(OverrideTable)).one()


# --- notification on request --------------------------------------------------


def test_requesting_an_override_emails_the_other_parent(
    client_fixture: TestClient, session_fixture: Session, notifier: FakeNotifier
) -> None:
    _seed_parents(session_fixture)
    _act_as(101, "Parent A")

    response = client_fixture.post(
        "/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD
    )

    assert response.status_code == 200
    assert len(notifier.sent) == 1
    recipient, subject, body = notifier.sent[0]
    assert recipient == PARENT_B_EMAIL
    assert "2026-08-07" in f"{subject}{body}"


def test_requesting_an_override_sms_pings_the_other_parent(
    client_fixture: TestClient,
    session_fixture: Session,
    notifier: FakeNotifier,
    sms: FakeSmsGateway,
) -> None:
    _seed_parents(session_fixture)
    _act_as(101, "Parent A")

    response = client_fixture.post(
        "/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD
    )

    assert response.status_code == 200
    assert len(sms.sent) == 1
    to, body = sms.sent[0]
    assert to == PARENT_B_PHONE
    assert "2026-08-07" in body
    assert "Parent A" in body
    assert len(notifier.sent) == 1  # email still sent


def test_web_create_skips_sms_when_counterparty_opted_out(
    client_fixture: TestClient,
    session_fixture: Session,
    notifier: FakeNotifier,
    sms: FakeSmsGateway,
) -> None:
    _seed_parents(session_fixture)
    SqlOptOutStore(session_fixture).opt_out(PARENT_B_PHONE)
    _act_as(101, "Parent A")

    response = client_fixture.post(
        "/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD
    )

    assert response.status_code == 200
    assert sms.sent == []
    assert len(notifier.sent) == 1


def test_web_create_skips_sms_when_counterparty_has_no_phone(
    client_fixture: TestClient,
    session_fixture: Session,
    notifier: FakeNotifier,
    sms: FakeSmsGateway,
) -> None:
    _seed_parents(session_fixture, parent_b_phone=None)
    _act_as(101, "Parent A")

    response = client_fixture.post(
        "/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD
    )

    assert response.status_code == 200
    assert sms.sent == []
    assert len(notifier.sent) == 1
    body = response.json()
    assert body["sms_notify_status"] == "skipped_no_phone"
    assert body["email_notify_status"] == "queued"


def test_web_create_records_opt_out_and_sent_statuses(
    client_fixture: TestClient,
    session_fixture: Session,
    notifier: FakeNotifier,
    sms: FakeSmsGateway,
) -> None:
    _seed_parents(session_fixture)
    SqlOptOutStore(session_fixture).opt_out(PARENT_B_PHONE)
    _act_as(101, "Parent A")

    response = client_fixture.post(
        "/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD
    )

    assert response.status_code == 200
    assert response.json()["sms_notify_status"] == "skipped_opt_out"
    session_fixture.expire_all()
    row = _pending_row(session_fixture)
    assert row.sms_notify_status == "skipped_opt_out"
    assert row.email_notify_status == "sent"


def test_web_create_marks_channels_sent_after_background_delivery(
    client_fixture: TestClient,
    session_fixture: Session,
    notifier: FakeNotifier,
    sms: FakeSmsGateway,
) -> None:
    _seed_parents(session_fixture)
    _act_as(101, "Parent A")

    response = client_fixture.post(
        "/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD
    )

    assert response.status_code == 200
    # Response is serialized before background tasks finish updating.
    assert response.json()["email_notify_status"] == "queued"
    assert response.json()["sms_notify_status"] == "queued"
    session_fixture.expire_all()
    row = _pending_row(session_fixture)
    assert row.email_notify_status == "sent"
    assert row.sms_notify_status == "sent"


def test_failed_email_notify_is_audited(
    client_fixture: TestClient, session_fixture: Session
) -> None:
    class ExplodingNotifier:
        last_outcome = "sent"

        def send(self, *, to: str, subject: str, body: str) -> None:
            raise RuntimeError("mail server down")

    _seed_parents(session_fixture)
    app.dependency_overrides[get_notifier] = lambda: ExplodingNotifier()
    _act_as(101, "Parent A")

    response = client_fixture.post(
        "/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD
    )

    assert response.status_code == 200
    session_fixture.expire_all()
    row = _pending_row(session_fixture)
    assert row.email_notify_status == "failed"
    audits = session_fixture.exec(
        select(AuditLogTable).where(AuditLogTable.action_type == "email_send_failed")
    ).all()
    assert len(audits) == 1


def test_requester_is_never_emailed_about_their_own_request(
    client_fixture: TestClient, session_fixture: Session, notifier: FakeNotifier
) -> None:
    _seed_parents(session_fixture)
    _act_as(101, "Parent A")

    client_fixture.post("/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD)

    assert [to for to, _, _ in notifier.sent] == [PARENT_B_EMAIL]


# --- notification on decision -------------------------------------------------


def test_decision_emails_the_requester(
    client_fixture: TestClient, session_fixture: Session, notifier: FakeNotifier
) -> None:
    _seed_parents(session_fixture)
    _act_as(101, "Parent A")
    client_fixture.post("/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD)
    override_id = _pending_row(session_fixture).id
    notifier.sent.clear()

    _act_as(102, "Parent B")
    response = client_fixture.post(
        f"/api/v1/schedule/overrides/{override_id}/decision", json={"approve": True}
    )

    assert response.status_code == 200
    assert len(notifier.sent) == 1
    recipient, subject, body = notifier.sent[0]
    assert recipient == PARENT_A_EMAIL
    assert "approved" in f"{subject} {body}".lower()


# --- failure isolation --------------------------------------------------------


def test_notification_failure_does_not_fail_the_request(
    client_fixture: TestClient, session_fixture: Session
) -> None:
    class ExplodingNotifier:
        def send(self, *, to: str, subject: str, body: str) -> None:
            raise RuntimeError("mail server down")

    _seed_parents(session_fixture)
    app.dependency_overrides[get_notifier] = lambda: ExplodingNotifier()
    _act_as(101, "Parent A")

    response = client_fixture.post(
        "/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD
    )

    assert response.status_code == 200
    # The override is still persisted — the custody record is what matters.
    session_fixture.expire_all()
    assert _pending_row(session_fixture).status == OverrideStatus.PENDING.value


def test_missing_recipient_address_is_not_an_error(
    client_fixture: TestClient, session_fixture: Session, notifier: FakeNotifier
) -> None:
    _seed_parents(session_fixture, parent_b_email=None)
    _act_as(101, "Parent A")

    response = client_fixture.post(
        "/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD
    )

    assert response.status_code == 200
    assert notifier.sent == []
    assert response.json()["email_notify_status"] == "skipped_no_address"


# --- expired requests must not display as pending -----------------------------


def test_pending_list_excludes_expired_requests(
    client_fixture: TestClient, session_fixture: Session, notifier: FakeNotifier
) -> None:
    _seed_parents(session_fixture)
    now = _now()
    session_fixture.add(
        OverrideTable(
            family_id=1,
            override_date=datetime(2026, 8, 7).date(),
            assigned_parent=ParentRole.PARENT_B.value,
            override_type=OverrideType.MUTUAL_SWAP.value,
            description="stale",
            status=OverrideStatus.PENDING.value,
            requested_by_user_id=101,
            expires_at=now - timedelta(hours=1),
        )
    )
    session_fixture.add(
        OverrideTable(
            family_id=1,
            override_date=datetime(2026, 8, 9).date(),
            assigned_parent=ParentRole.PARENT_B.value,
            override_type=OverrideType.MUTUAL_SWAP.value,
            description="live",
            status=OverrideStatus.PENDING.value,
            requested_by_user_id=101,
            expires_at=now + timedelta(hours=1),
        )
    )
    session_fixture.commit()
    _act_as(102, "Parent B")

    response = client_fixture.get("/api/v1/schedule/overrides/pending")

    assert response.status_code == 200
    descriptions = [item["description"] for item in response.json()]
    assert descriptions == ["live"]


# --- audit history for the web path -------------------------------------------


def _audit_actions(session: Session) -> list[str]:
    return [row.action_type for row in session.exec(select(AuditLogTable)).all()]


def test_requesting_an_override_is_audited(
    client_fixture: TestClient, session_fixture: Session, notifier: FakeNotifier
) -> None:
    _seed_parents(session_fixture)
    _act_as(101, "Parent A")

    client_fixture.post("/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD)

    assert "override_requested" in _audit_actions(session_fixture)


@pytest.mark.parametrize(
    ("approve", "expected_action"),
    [(True, "override_approved"), (False, "override_rejected")],
)
def test_decision_is_audited(
    client_fixture: TestClient,
    session_fixture: Session,
    notifier: FakeNotifier,
    approve: bool,
    expected_action: str,
) -> None:
    _seed_parents(session_fixture)
    _act_as(101, "Parent A")
    client_fixture.post("/api/v1/schedule/overrides", json=OVERRIDE_PAYLOAD)
    override_id = _pending_row(session_fixture).id

    _act_as(102, "Parent B")
    client_fixture.post(
        f"/api/v1/schedule/overrides/{override_id}/decision",
        json={"approve": approve},
    )

    actions = _audit_actions(session_fixture)
    assert expected_action in actions
    audit_row = session_fixture.exec(
        select(AuditLogTable).where(AuditLogTable.action_type == expected_action)
    ).one()
    assert audit_row.previous_state_id == override_id
