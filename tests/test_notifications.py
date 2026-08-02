"""Notifier port, SMTP adapter, and the users.email schema migration.

The adapter mirrors EnvTwilioSmsGateway: it records every message, and only
reaches the network when fully configured. send() must never raise — a mail
failure must never fail an override.
"""

from datetime import date, datetime

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from api.email_notifier import SmtpEmailNotifier
from core.notifications import (
    FakeNotifier,
    override_decided_email,
    override_requested_email,
)
from database.schema import UserTable
from main import ensure_calendar_feed_token_column, ensure_user_email_column

SMTP_ENV = {
    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": "587",
    "SMTP_USERNAME": "family@example.com",
    "SMTP_PASSWORD": "app-password",
    "SMTP_FROM": "family@example.com",
}


class FakeSMTP:
    """Stands in for smtplib.SMTP; records the calls the adapter makes."""

    instances: list["FakeSMTP"] = []

    def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args: tuple[str, str] | None = None
        self.messages: list[object] = []
        self.raise_on_send: Exception | None = None
        FakeSMTP.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.login_args = (username, password)

    def send_message(self, message: object) -> None:
        if self.raise_on_send is not None:
            raise self.raise_on_send
        self.messages.append(message)


@pytest.fixture(autouse=True)
def _reset_fake_smtp() -> None:
    FakeSMTP.instances.clear()


def _use_fake_smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSMTP]:
    monkeypatch.setattr("api.email_notifier.smtplib.SMTP", FakeSMTP)
    return FakeSMTP


def _configure_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in SMTP_ENV.items():
        monkeypatch.setenv(key, value)


# --- message builders (pure) --------------------------------------------------


def test_requested_email_names_date_parent_and_type() -> None:
    subject, body = override_requested_email(
        requester_label="Parent A",
        override_date=date(2026, 8, 7),
        override_type="Mutual Swap",
        description="soccer tournament",
        expires_at=datetime(2026, 8, 1, 12, 0),
    )
    combined = f"{subject}\n{body}"
    assert "2026-08-07" in combined
    assert "Parent A" in combined
    assert "Mutual Swap" in combined
    assert "soccer tournament" in combined


def test_decided_email_states_the_outcome() -> None:
    approved_subject, approved_body = override_decided_email(
        decider_label="Parent B", override_date=date(2026, 8, 7), approved=True
    )
    rejected_subject, rejected_body = override_decided_email(
        decider_label="Parent B", override_date=date(2026, 8, 7), approved=False
    )
    assert "approved" in f"{approved_subject} {approved_body}".lower()
    assert "declined" in f"{rejected_subject} {rejected_body}".lower()
    assert "2026-08-07" in f"{approved_subject}{approved_body}"


def test_fake_notifier_records_messages() -> None:
    notifier = FakeNotifier()
    notifier.send(to="a@example.com", subject="s", body="b")
    assert notifier.sent == [("a@example.com", "s", "b")]


# --- SMTP adapter -------------------------------------------------------------


def test_unconfigured_adapter_records_but_never_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No SMTP env -> local dev and unconfigured deploys behave as before."""
    fake = _use_fake_smtp(monkeypatch)
    notifier = SmtpEmailNotifier()

    notifier.send(to="b@example.com", subject="Swap request", body="details")

    assert notifier.sent == [("b@example.com", "Swap request", "details")]
    assert fake.instances == []


def test_configured_adapter_uses_starttls_and_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_smtp(monkeypatch)
    fake = _use_fake_smtp(monkeypatch)

    SmtpEmailNotifier().send(
        to="b@example.com", subject="Swap request", body="details"
    )

    assert len(fake.instances) == 1
    smtp = fake.instances[0]
    assert (smtp.host, smtp.port) == ("smtp.gmail.com", 587)
    assert smtp.started_tls is True
    assert smtp.login_args == ("family@example.com", "app-password")
    assert len(smtp.messages) == 1


def test_send_swallows_smtp_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A mail failure must never propagate — an override must not fail because
    the mail server is down."""
    import smtplib

    _configure_smtp(monkeypatch)
    fake = _use_fake_smtp(monkeypatch)

    original_init = fake.__init__

    def _init_raising(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        original_init(self, *args, **kwargs)
        self.raise_on_send = smtplib.SMTPException("mailbox unavailable")

    monkeypatch.setattr(fake, "__init__", _init_raising)

    notifier = SmtpEmailNotifier()
    notifier.send(to="b@example.com", subject="s", body="b")  # must not raise

    assert notifier.sent == [("b@example.com", "s", "b")]


def test_send_swallows_connection_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_smtp(monkeypatch)

    def _explode(*args: object, **kwargs: object) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr("api.email_notifier.smtplib.SMTP", _explode)

    SmtpEmailNotifier().send(to="b@example.com", subject="s", body="b")


# --- users.email migration ----------------------------------------------------


def _engine_with_legacy_users_table():
    """A DB whose users table predates the email column, as on the Fly volume."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE users ("
            " id INTEGER PRIMARY KEY,"
            " family_id INTEGER NOT NULL,"
            " role VARCHAR NOT NULL,"
            " phone VARCHAR,"
            " custody_label VARCHAR,"
            " passcode_hash VARCHAR)"
        )
        conn.exec_driver_sql(
            "INSERT INTO users (id, family_id, role) VALUES (101, 1, 'Parent')"
        )
        conn.commit()
    return engine


def _columns(engine) -> set[str]:
    with engine.connect() as conn:
        return {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(users)")}


def test_migration_adds_missing_email_column() -> None:
    """SQLModel.create_all() adds tables, never columns — without this the
    deployed app crashes on boot with 'no such column: users.email'."""
    engine = _engine_with_legacy_users_table()
    assert "email" not in _columns(engine)

    ensure_user_email_column(engine)

    assert "email" in _columns(engine)
    # Bring the legacy table in line with the current ORM model before reading
    # (production lifespan runs all ensure_* migrations in sequence).
    ensure_calendar_feed_token_column(engine)
    # Existing rows survive and read back through the ORM.
    with Session(engine) as session:
        user = session.exec(select(UserTable).where(UserTable.id == 101)).one()
        assert user.email is None


def test_migration_is_idempotent() -> None:
    engine = _engine_with_legacy_users_table()
    ensure_user_email_column(engine)
    ensure_user_email_column(engine)  # must not raise "duplicate column name"
    assert "email" in _columns(engine)


def test_migration_no_ops_on_a_fresh_database() -> None:
    """create_all() already includes email on a fresh DB; the helper must not
    trip over a users table it did not have to patch."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    ensure_user_email_column(engine)
    assert "email" in _columns(engine)
