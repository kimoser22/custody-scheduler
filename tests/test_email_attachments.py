"""Attachment support on the SMTP notifier, without disturbing existing sends."""

from email import message_from_bytes

import pytest

from api.email_notifier import SmtpEmailNotifier


class _CapturingSMTP:
    """Stands in for smtplib.SMTP; records the message it is asked to send."""

    last_message = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, *args):
        pass

    def send_message(self, message):
        _CapturingSMTP.last_message = message


@pytest.fixture(name="configured_notifier")
def _configured_notifier(monkeypatch: pytest.MonkeyPatch) -> SmtpEmailNotifier:
    for key, value in {
        "SMTP_HOST": "smtp.test", "SMTP_PORT": "587",
        "SMTP_USERNAME": "u", "SMTP_PASSWORD": "p",
        "SMTP_FROM": "from@test",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr("api.email_notifier.smtplib.SMTP", _CapturingSMTP)
    _CapturingSMTP.last_message = None
    return SmtpEmailNotifier()


def test_send_with_outcome_attaches_the_archive(
    configured_notifier: SmtpEmailNotifier,
) -> None:
    payload = b'{"archive_manifest": {}}'

    outcome = configured_notifier.send_with_outcome(
        to="a@example.com",
        subject="Custody record archive",
        body="hashes here",
        attachments=[("custody-export-2026-08-16.json", payload)],
    )

    assert outcome == "submitted"
    raw = _CapturingSMTP.last_message.as_bytes()
    parsed = message_from_bytes(raw)
    attachments = [p for p in parsed.walk() if p.get_filename()]
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "custody-export-2026-08-16.json"
    assert attachments[0].get_payload(decode=True) == payload


def test_unconfigured_smtp_is_not_reported_as_submitted() -> None:
    """Nothing reached any SMTP server, so the archival path must not be told
    it did — "submitted" here would let a config regression produce green
    backups that deliver nothing. Plain send() keeps its no-op behavior."""
    notifier = SmtpEmailNotifier()  # env stripped by conftest -> unconfigured
    assert (
        notifier.send_with_outcome(to="a@x", subject="s", body="b")
        == "not_configured"
    )


def test_plain_send_is_unchanged(
    configured_notifier: SmtpEmailNotifier,
) -> None:
    """Existing call sites must see identical behavior — no attachment part."""
    configured_notifier.send(to="a@example.com", subject="s", body="hello")

    parsed = message_from_bytes(_CapturingSMTP.last_message.as_bytes())
    assert not parsed.is_multipart()
    assert parsed.get_payload().strip() == "hello"
