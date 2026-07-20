import base64
import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from api.twilio_webhook import get_concierge_runner
from concierge.runner import RecordingConciergeRunner
from database.schema import OverrideTable, UserTable
from main import app


def _twilio_signature(auth_token: str, url: str, params: dict[str, str]) -> str:
    """Independent reimplementation of Twilio's documented signing algorithm,
    used to verify api.twilio_webhook's validator against the real spec
    rather than against itself."""
    data = url + "".join(f"{key}{params[key]}" for key in sorted(params))
    digest = hmac.new(auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("utf-8")


def test_twilio_webhook_invokes_runner_and_returns_twiml(
    client_fixture: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TWILIO_ALLOW_UNVERIFIED", "1")
    runner = RecordingConciergeRunner(response={"status": "ok"})
    app.dependency_overrides[get_concierge_runner] = lambda: runner

    response = client_fixture.post(
        "/api/v1/twilio/sms",
        data={
            "MessageSid": "SMabc",
            "From": "+15550001",
            "Body": "swap july 8",
        },
    )

    assert response.status_code == 200
    assert "Response" in response.text
    assert runner.calls == [
        {
            "message_sid": "SMabc",
            "from_phone": "+15550001",
            "body": "swap july 8",
        }
    ]
    app.dependency_overrides.pop(get_concierge_runner, None)


def test_twilio_webhook_silent_on_dropped(
    client_fixture: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TWILIO_ALLOW_UNVERIFIED", "1")
    runner = RecordingConciergeRunner(response={"status": "dropped"})
    app.dependency_overrides[get_concierge_runner] = lambda: runner

    response = client_fixture.post(
        "/api/v1/twilio/sms",
        data={"MessageSid": "SMdup", "From": "+15550001", "Body": "hi"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    app.dependency_overrides.pop(get_concierge_runner, None)


def test_twilio_webhook_silent_on_unknown_sender(
    client_fixture: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TWILIO_ALLOW_UNVERIFIED", "1")
    runner = RecordingConciergeRunner(response={"status": "ignored", "reason": "unknown_sender"})
    app.dependency_overrides[get_concierge_runner] = lambda: runner

    response = client_fixture.post(
        "/api/v1/twilio/sms",
        data={"MessageSid": "SMx", "From": "+1000", "Body": "hi"},
    )

    assert response.status_code == 200
    app.dependency_overrides.pop(get_concierge_runner, None)


def test_twilio_webhook_rejects_when_unconfigured_by_default(
    client_fixture: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail closed: with no TWILIO_AUTH_TOKEN and no explicit opt-out, the
    webhook must reject rather than trust attacker-controlled form fields."""
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TWILIO_ALLOW_UNVERIFIED", raising=False)
    runner = RecordingConciergeRunner(response={"status": "ok"})
    app.dependency_overrides[get_concierge_runner] = lambda: runner

    response = client_fixture.post(
        "/api/v1/twilio/sms",
        data={"MessageSid": "SMnosig", "From": "+15550001", "Body": "hi"},
    )

    assert response.status_code == 403
    assert runner.calls == []
    app.dependency_overrides.pop(get_concierge_runner, None)


def test_twilio_webhook_skips_only_with_explicit_local_optin(
    client_fixture: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Local dev / simulator escape hatch: verification is skipped only when
    TWILIO_ALLOW_UNVERIFIED is explicitly set (mirrors ALLOW_SQLITE_SCHEMA_RESET)."""
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("TWILIO_ALLOW_UNVERIFIED", "1")
    runner = RecordingConciergeRunner(response={"status": "ok"})
    app.dependency_overrides[get_concierge_runner] = lambda: runner

    response = client_fixture.post(
        "/api/v1/twilio/sms",
        data={"MessageSid": "SMnosig", "From": "+15550001", "Body": "hi"},
    )

    assert response.status_code == 200
    assert runner.calls
    app.dependency_overrides.pop(get_concierge_runner, None)


def test_twilio_webhook_accepts_valid_signature_when_configured(
    client_fixture: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-auth-token")
    runner = RecordingConciergeRunner(response={"status": "ok"})
    app.dependency_overrides[get_concierge_runner] = lambda: runner

    params = {"MessageSid": "SMsig1", "From": "+15550001", "Body": "hi"}
    signature = _twilio_signature(
        "test-auth-token", "http://testserver/api/v1/twilio/sms", params
    )

    response = client_fixture.post(
        "/api/v1/twilio/sms",
        data=params,
        headers={"X-Twilio-Signature": signature},
    )

    assert response.status_code == 200
    assert runner.calls
    app.dependency_overrides.pop(get_concierge_runner, None)


def test_twilio_webhook_rejects_wrong_signature_when_configured(
    client_fixture: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-auth-token")
    runner = RecordingConciergeRunner(response={"status": "ok"})
    app.dependency_overrides[get_concierge_runner] = lambda: runner

    response = client_fixture.post(
        "/api/v1/twilio/sms",
        data={"MessageSid": "SMsig2", "From": "+15550001", "Body": "hi"},
        headers={"X-Twilio-Signature": "not-the-real-signature"},
    )

    assert response.status_code == 403
    assert runner.calls == []
    app.dependency_overrides.pop(get_concierge_runner, None)


def test_twilio_webhook_rejects_missing_signature_when_configured(
    client_fixture: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-auth-token")
    runner = RecordingConciergeRunner(response={"status": "ok"})
    app.dependency_overrides[get_concierge_runner] = lambda: runner

    response = client_fixture.post(
        "/api/v1/twilio/sms",
        data={"MessageSid": "SMsig3", "From": "+15550001", "Body": "hi"},
    )

    assert response.status_code == 403
    assert runner.calls == []
    app.dependency_overrides.pop(get_concierge_runner, None)


def test_twilio_webhook_uses_the_request_scoped_session_not_a_leaked_one(
    client_fixture: TestClient,
    session_fixture: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test: get_concierge_runner previously built its own
    Session(engine) pointing at the real database.connection.engine,
    ignoring any FastAPI Depends(get_session) override — and never closed
    it. It must now depend on SessionDep like every other route so it uses
    the same request-scoped (and here, test-overridden) session. Proven by
    resolving a phone number that only exists in the test DB, through the
    real (non-Recording) get_concierge_runner."""
    monkeypatch.setenv("TWILIO_ALLOW_UNVERIFIED", "1")
    session_fixture.add(
        UserTable(
            id=9101,
            family_id=1,
            role="Parent",
            phone="+19995551234",
            custody_label="Parent A",
        )
    )
    session_fixture.commit()

    response = client_fixture.post(
        "/api/v1/twilio/sms",
        data={
            "MessageSid": "SM-session-wiring",
            "From": "+19995551234",
            "Body": "swap please",
        },
    )

    assert response.status_code == 200
    # If the runner had instead opened its own session against the real
    # custody.db, this phone number wouldn't resolve there and no draft
    # would have been created in the test session.
    drafts = session_fixture.exec(
        select(OverrideTable).where(OverrideTable.requested_by_user_id == 9101)
    ).all()
    assert len(drafts) == 1
