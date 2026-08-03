"""A failed Twilio send must never fail the custody operation it describes.

Every other notification path already honors this: SmtpEmailNotifier swallows
and logs, and _send_safely wraps the web notifier. SMS was the exception —
messages.create() raised straight out of the webhook handler, and because
handle_sms claims the message_sid *first*, Twilio's retry of the resulting 500
is dropped as a duplicate. The inbound is consumed, the outbound never goes.

Error 21610 ("recipient opted out") is treated specially: Twilio maintains its
own opt-out list, and a rejection tells us something our sms_opt_outs table
does not know. We record it so the two lists converge.
"""

import logging

import pytest
from twilio.base.exceptions import TwilioRestException

from concierge.adapters import EnvTwilioSmsGateway
from concierge.ports import (
    InMemoryOptOutStore,
    OptOutAwareSmsGateway,
    RecipientOptedOutError,
)

TO = "+15558675309"
BODY = "Parent A requested a schedule change for 2026-08-07."

TWILIO_ENV = {
    "TWILIO_ACCOUNT_SID": "AC-test",
    "TWILIO_AUTH_TOKEN": "token-test",
    "TWILIO_FROM_NUMBER": "+15550000000",
}


class FakeMessages:
    def __init__(self, error: Exception | None) -> None:
        self._error = error
        self.calls: list[dict] = []

    def create(self, **kwargs) -> object:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return object()


class FakeClient:
    """Stands in for twilio.rest.Client. The adapter imports it lazily inside
    send(), so patching the module attribute is enough."""

    instances: list["FakeClient"] = []
    error: Exception | None = None

    def __init__(self, account_sid: str, auth_token: str) -> None:
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.messages = FakeMessages(FakeClient.error)
        FakeClient.instances.append(self)


@pytest.fixture(autouse=True)
def _reset_fake_client() -> None:
    FakeClient.instances.clear()
    FakeClient.error = None


def _use_fake_client(monkeypatch: pytest.MonkeyPatch, error: Exception | None = None):
    FakeClient.error = error
    monkeypatch.setattr("twilio.rest.Client", FakeClient)
    return FakeClient


def _configure(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in TWILIO_ENV.items():
        monkeypatch.setenv(key, value)


def _rest_error(*, status: int, code: int) -> TwilioRestException:
    return TwilioRestException(status=status, uri="/Messages", msg="boom", code=code)


# --- failures are swallowed, never raised -------------------------------------


def test_transient_twilio_failure_is_swallowed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _configure(monkeypatch)
    _use_fake_client(monkeypatch, _rest_error(status=500, code=20500))
    gateway = EnvTwilioSmsGateway()

    with caplog.at_level(logging.WARNING):
        gateway.send(TO, BODY)  # must not raise

    assert gateway.sent == [(TO, BODY)]
    assert any("20500" in record.getMessage() for record in caplog.records)


def test_connection_failure_is_swallowed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _configure(monkeypatch)
    _use_fake_client(monkeypatch, OSError("connection refused"))

    with caplog.at_level(logging.WARNING):
        EnvTwilioSmsGateway().send(TO, BODY)  # must not raise

    assert any(record.levelno >= logging.WARNING for record in caplog.records)


def test_bad_credentials_do_not_break_the_webhook(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A misconfigured token must degrade to a logged failure, not a 500 that
    Twilio retries into a duplicate-dropped dead end."""
    _configure(monkeypatch)
    _use_fake_client(monkeypatch, _rest_error(status=401, code=20003))

    with caplog.at_level(logging.WARNING):
        EnvTwilioSmsGateway().send(TO, BODY)  # must not raise

    assert any("20003" in record.getMessage() for record in caplog.records)


# --- 21610 self-heals into the local opt-out store -----------------------------


def test_opted_out_rejection_records_the_opt_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Twilio's opt-out list is authoritative and ours may lag it. A 21610
    rejection is the moment to catch up, so we stop attempting sends they will
    always refuse."""
    _configure(monkeypatch)
    _use_fake_client(monkeypatch, _rest_error(status=400, code=21610))
    opt_outs = InMemoryOptOutStore()
    gateway = OptOutAwareSmsGateway(EnvTwilioSmsGateway(), opt_outs)

    gateway.send(TO, BODY)  # must not raise

    assert opt_outs.is_opted_out(TO) is True


def test_opted_out_rejection_on_forced_send_also_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keyword ACKs bypass our gate by design; they must still not raise when
    Twilio refuses them."""
    _configure(monkeypatch)
    _use_fake_client(monkeypatch, _rest_error(status=400, code=21610))
    opt_outs = InMemoryOptOutStore()
    gateway = OptOutAwareSmsGateway(EnvTwilioSmsGateway(), opt_outs)

    gateway.send_forced(TO, "You have opted out.")  # must not raise

    assert opt_outs.is_opted_out(TO) is True


def test_second_send_after_self_heal_never_reaches_twilio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The point of recording it: the next send is short-circuited by our own
    gate rather than rejected by Twilio again."""
    _configure(monkeypatch)
    fake = _use_fake_client(monkeypatch, _rest_error(status=400, code=21610))
    gateway = OptOutAwareSmsGateway(EnvTwilioSmsGateway(), InMemoryOptOutStore())

    gateway.send(TO, BODY)
    calls_after_first = len(fake.instances)
    gateway.send(TO, BODY)

    assert len(fake.instances) == calls_after_first


def test_bare_gateway_raises_the_translated_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The adapter translates 21610 rather than swallowing it, so the wrapper
    that owns the opt-out store can react. Ungated callers see the domain
    error, never a raw TwilioRestException."""
    _configure(monkeypatch)
    _use_fake_client(monkeypatch, _rest_error(status=400, code=21610))

    with pytest.raises(RecipientOptedOutError):
        EnvTwilioSmsGateway().send(TO, BODY)


# --- unchanged behavior --------------------------------------------------------


def test_successful_send_is_unchanged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _configure(monkeypatch)
    fake = _use_fake_client(monkeypatch)

    with caplog.at_level(logging.WARNING):
        EnvTwilioSmsGateway().send(TO, BODY)

    assert len(fake.instances) == 1
    assert fake.instances[0].messages.calls == [
        {"to": TO, "from_": TWILIO_ENV["TWILIO_FROM_NUMBER"], "body": BODY}
    ]
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_unconfigured_gateway_never_constructs_a_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guards the early return: adding try/except must not accidentally start
    reaching for Twilio when credentials are absent."""
    for key in TWILIO_ENV:
        monkeypatch.delenv(key, raising=False)
    fake = _use_fake_client(monkeypatch, _rest_error(status=500, code=20500))

    gateway = EnvTwilioSmsGateway()
    gateway.send(TO, BODY)

    assert gateway.sent == [(TO, BODY)]
    assert fake.instances == []
