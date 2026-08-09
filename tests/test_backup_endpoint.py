"""POST /api/v1/admin/backup-email — the weekly evidence-archive trigger.

The invariants under test (see core/backup.py):
1. One backup_date = one immutable byte sequence, however many attempts.
2. `submitted` means the exact bytes reached SMTP for every required parent
   IDENTITY; only submitted records join the hash chain.
3. At most one process owns delivery at any instant (lease).

The negative assertions matter most: a failed email must never produce a green
result, and a calendar rollover must never abandon an archive.
"""

import hashlib
import json
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

import api.backup_router as backup_router
from api.dependencies import get_notifier
from database.schema import (
    AuditLogTable,
    BackupDeliveryTable,
    BackupRecordTable,
    UserTable,
)
from main import app

TOKEN = "test-backup-trigger-token"
DAY1 = date(2026, 8, 16)
DAY2 = date(2026, 8, 17)
NOW = datetime(2026, 8, 16, 3, 17, 12)


class RecordingNotifier:
    """send_with_outcome records every send; addresses in `failing` fail."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str, list | None]] = []
        self.failing: set[str] = set()

    def send(self, *, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body, None))

    def send_with_outcome(
        self, *, to: str, subject: str, body: str, attachments=None
    ) -> str:
        self.sent.append((to, subject, body, attachments))
        return "failed" if to in self.failing else "submitted"


@pytest.fixture(name="notifier")
def _notifier() -> RecordingNotifier:
    return RecordingNotifier()


@pytest.fixture(name="backup_env")
def _backup_env(
    client_fixture: TestClient,
    session_fixture: Session,
    notifier: RecordingNotifier,
    monkeypatch: pytest.MonkeyPatch,
):
    """Token set, both parents seeded with emails, clock pinned to DAY1."""
    monkeypatch.setenv("BACKUP_TRIGGER_TOKEN", TOKEN)
    session_fixture.add(
        UserTable(id=101, family_id=1, role="Parent", phone="+15550001",
                  custody_label="Parent A", email="a@example.com")
    )
    session_fixture.add(
        UserTable(id=102, family_id=1, role="Parent", phone="+15550002",
                  custody_label="Parent B", email="b@example.com")
    )
    session_fixture.commit()
    app.dependency_overrides[get_notifier] = lambda: notifier
    monkeypatch.setattr(backup_router, "household_today", lambda: DAY1)
    monkeypatch.setattr(backup_router, "_utcnow", lambda: NOW)
    return client_fixture


def _trigger(client: TestClient, token: str = TOKEN):
    return client.post(
        "/api/v1/admin/backup-email",
        headers={"Authorization": f"Bearer {token}"},
    )


def _rows(session: Session) -> list[BackupRecordTable]:
    return list(session.exec(select(BackupRecordTable)).all())


def _deliveries(session: Session) -> list[BackupDeliveryTable]:
    return list(session.exec(select(BackupDeliveryTable)).all())


# --- auth (fail-closed, before any work) ---------------------------------------


def test_unconfigured_token_is_503(
    backup_env, session_fixture: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BACKUP_TRIGGER_TOKEN", raising=False)
    assert _trigger(backup_env).status_code == 503
    assert _rows(session_fixture) == []


def test_wrong_token_is_403(backup_env, session_fixture: Session) -> None:
    assert _trigger(backup_env, token="wrong").status_code == 403
    assert _rows(session_fixture) == []


# --- happy path ----------------------------------------------------------------


def test_happy_path_submits_to_both_parents(
    backup_env, session_fixture: Session, notifier: RecordingNotifier
) -> None:
    response = _trigger(backup_env)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "submitted"
    assert body["backup_date"] == DAY1.isoformat()
    assert body["prev_sha256"] is None  # first link

    # Two separate sends, one per identity, each carrying the archive.
    assert [s[0] for s in notifier.sent] == ["a@example.com", "b@example.com"]
    attachment_name, attachment_bytes = notifier.sent[0][3][0]
    assert attachment_name == f"custody-export-{DAY1.isoformat()}.json"
    digest = hashlib.sha256(attachment_bytes).hexdigest()
    assert digest == body["sha256"]
    assert body["sha256"] in notifier.sent[0][1]  # hash in the subject

    row = _rows(session_fixture)[0]
    assert row.status == "submitted"
    assert row.sha256 == digest
    assert row.archive_bytes is None  # cleared on the submitted transition

    outcomes = {(d.parent_id, d.outcome) for d in _deliveries(session_fixture)}
    assert outcomes == {(101, "submitted"), (102, "submitted")}

    audit = session_fixture.exec(
        select(AuditLogTable).where(AuditLogTable.action_type == "backup_submitted")
    ).first()
    assert audit is not None and digest in audit.description


def test_archive_manifest_freezes_identities_and_format(
    backup_env, notifier: RecordingNotifier
) -> None:
    _trigger(backup_env)
    doc = json.loads(notifier.sent[0][3][0][1].decode("utf-8"))

    manifest = doc["archive_manifest"]
    assert manifest["format"] == "custody-archive"
    assert manifest["archive_format_version"] == 1
    assert manifest["backup_date"] == DAY1.isoformat()
    assert manifest["recipient_parent_ids"] == [101, 102]
    assert doc["data"]["schema_version"] == 2
    assert "backup_records" in doc["data"]


def test_idempotent_same_day_returns_same_hash_no_second_email(
    backup_env, session_fixture: Session, notifier: RecordingNotifier
) -> None:
    first = _trigger(backup_env).json()
    sends_after_first = len(notifier.sent)

    second = _trigger(backup_env)

    assert second.status_code == 200
    assert second.json()["sha256"] == first["sha256"]
    assert len(notifier.sent) == sends_after_first
    assert len(_rows(session_fixture)) == 1


# --- failure semantics ---------------------------------------------------------


def test_smtp_failure_is_red_and_does_not_satisfy_idempotency(
    backup_env, session_fixture: Session, notifier: RecordingNotifier
) -> None:
    notifier.failing = {"a@example.com", "b@example.com"}

    response = _trigger(backup_env)

    assert response.status_code == 502
    assert response.json()["status"] == "failed"
    row = _rows(session_fixture)[0]
    assert row.status == "failed"
    # Failure path keeps the bytes: they ARE the retry state, and they must be
    # exactly what the notifier saw.
    assert row.archive_bytes == notifier.sent[0][3][0][1]

    # Retry succeeds and satisfies idempotency only now.
    notifier.failing = set()
    retry = _trigger(backup_env)
    assert retry.status_code == 200
    assert retry.json()["status"] == "submitted"


def test_retries_resend_identical_bytes_despite_data_changes(
    backup_env, session_fixture: Session, notifier: RecordingNotifier
) -> None:
    """Invariant 1. Custody data changing between attempts must not fork the
    archive: the retry resends the stored bytes, hash unchanged."""
    notifier.failing = {"b@example.com"}
    first_hash = _trigger(backup_env).json()["sha256"]
    original_bytes = notifier.sent[0][3][0][1]

    # The world changes between attempts.
    session_fixture.add(
        UserTable(id=999, family_id=1, role="Viewer", custody_label=None)
    )
    session_fixture.commit()

    notifier.failing = set()
    retry = _trigger(backup_env)

    assert retry.json()["sha256"] == first_hash
    assert notifier.sent[-1][3][0][1] == original_bytes


def test_partial_delivery_fails_overall_and_retries_both(
    backup_env, session_fixture: Session, notifier: RecordingNotifier
) -> None:
    """Duplicates over gaps: the parent who already got it gets it again."""
    notifier.failing = {"b@example.com"}
    assert _trigger(backup_env).status_code == 502

    by_attempt = {(d.attempt_no, d.parent_id): d for d in _deliveries(session_fixture)}
    assert by_attempt[(1, 101)].outcome == "submitted"
    assert by_attempt[(1, 102)].outcome == "failed"

    notifier.failing = set()
    assert _trigger(backup_env).status_code == 200

    recipients = [s[0] for s in notifier.sent]
    assert recipients == [
        "a@example.com", "b@example.com",  # attempt 1
        "a@example.com", "b@example.com",  # attempt 2: both again
    ]
    by_attempt = {(d.attempt_no, d.parent_id): d for d in _deliveries(session_fixture)}
    assert by_attempt[(2, 101)].outcome == "submitted"
    assert by_attempt[(2, 102)].outcome == "submitted"


def test_address_corrected_between_attempts(
    backup_env, session_fixture: Session, notifier: RecordingNotifier
) -> None:
    """Identities are frozen in the archive; addresses are operational and may
    be fixed between attempts without touching the bytes."""
    notifier.failing = {"b@example.com"}
    first_hash = _trigger(backup_env).json()["sha256"]

    parent_b = session_fixture.get(UserTable, 102)
    parent_b.email = "b-corrected@example.com"
    session_fixture.add(parent_b)
    session_fixture.commit()

    notifier.failing = set()
    retry = _trigger(backup_env)

    assert retry.status_code == 200
    assert retry.json()["sha256"] == first_hash  # bytes unchanged
    assert notifier.sent[-1][0] == "b-corrected@example.com"
    addresses = {
        (d.attempt_no, d.address_used) for d in _deliveries(session_fixture)
        if d.parent_id == 102
    }
    assert addresses == {(1, "b@example.com"), (2, "b-corrected@example.com")}


def test_parent_without_email_blocks_submission_but_stays_required(
    backup_env, session_fixture: Session, notifier: RecordingNotifier
) -> None:
    parent_b = session_fixture.get(UserTable, 102)
    parent_b.email = None
    session_fixture.add(parent_b)
    session_fixture.commit()

    response = _trigger(backup_env)

    assert response.status_code == 502
    doc = json.loads(notifier.sent[0][3][0][1].decode("utf-8"))
    assert doc["archive_manifest"]["recipient_parent_ids"] == [101, 102]
    failed = [d for d in _deliveries(session_fixture) if d.parent_id == 102]
    assert failed[0].outcome == "failed"
    assert failed[0].error_class == "no_address"


def test_zero_parents_with_email_is_503_nothing_recorded(
    backup_env, session_fixture: Session
) -> None:
    for uid in (101, 102):
        user = session_fixture.get(UserTable, uid)
        user.email = None
        session_fixture.add(user)
    session_fixture.commit()

    assert _trigger(backup_env).status_code == 503
    assert _rows(session_fixture) == []


# --- cross-midnight and the chain ----------------------------------------------


def test_cross_midnight_retry_resends_original_not_new_date(
    backup_env, session_fixture: Session, notifier: RecordingNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The DST-window bug: a failure at 23:17 Eastern retried after midnight
    must resolve the ORIGINAL archive and stop — one invocation, one archive."""
    notifier.failing = {"b@example.com"}
    first_hash = _trigger(backup_env).json()["sha256"]

    # Midnight passes.
    monkeypatch.setattr(backup_router, "household_today", lambda: DAY2)
    notifier.failing = set()

    response = _trigger(backup_env)

    assert response.status_code == 200
    body = response.json()
    assert body["backup_date"] == DAY1.isoformat()  # the original, not DAY2
    assert body["sha256"] == first_hash
    assert len(_rows(session_fixture)) == 1  # DAY2 not claimed by this call

    # The NEXT invocation claims the new date and links to the resolved hash.
    nxt = _trigger(backup_env).json()
    assert nxt["backup_date"] == DAY2.isoformat()
    assert nxt["prev_sha256"] == first_hash


def test_chain_links_to_last_submitted(
    backup_env, session_fixture: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    day1 = _trigger(backup_env).json()
    monkeypatch.setattr(backup_router, "household_today", lambda: DAY2)
    day2 = _trigger(backup_env).json()

    assert day1["prev_sha256"] is None
    assert day2["prev_sha256"] == day1["sha256"]


def test_abandon_is_explicit_and_lets_the_chain_move_on(
    backup_env, session_fixture: Session, notifier: RecordingNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notifier.failing = {"a@example.com", "b@example.com"}
    _trigger(backup_env)

    response = backup_env.post(
        "/api/v1/admin/backup-abandon",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 200

    row = _rows(session_fixture)[0]
    assert row.status == "abandoned"
    audit = session_fixture.exec(
        select(AuditLogTable).where(AuditLogTable.action_type == "backup_abandoned")
    ).first()
    assert audit is not None

    # Chain skips the abandoned link.
    monkeypatch.setattr(backup_router, "household_today", lambda: DAY2)
    notifier.failing = set()
    nxt = _trigger(backup_env).json()
    assert nxt["backup_date"] == DAY2.isoformat()
    assert nxt["prev_sha256"] is None  # nothing submitted before it


# --- lease / concurrency -------------------------------------------------------


def test_live_pending_lease_is_409(
    backup_env, session_fixture: Session
) -> None:
    session_fixture.add(
        BackupRecordTable(
            backup_date=DAY1, created_at=NOW, sha256="f" * 64,
            prev_sha256=None, archive_bytes=b"{}", status="pending",
            attempt_started_at=NOW,
            lease_expires_at=NOW + timedelta(minutes=9),
        )
    )
    session_fixture.commit()

    assert _trigger(backup_env).status_code == 409


def test_expired_pending_lease_is_taken_over_and_resent(
    backup_env, session_fixture: Session, notifier: RecordingNotifier
) -> None:
    """Crash recovery: the process died mid-send 20 minutes ago; its stored
    bytes are resent verbatim — no rebuild."""
    stored = json.dumps({
        "archive_manifest": {"backup_date": DAY1.isoformat(),
                             "recipient_parent_ids": [101, 102]},
        "data": {},
    }).encode()
    session_fixture.add(
        BackupRecordTable(
            backup_date=DAY1, created_at=NOW - timedelta(minutes=20),
            sha256=hashlib.sha256(stored).hexdigest(), prev_sha256=None,
            archive_bytes=stored, status="pending",
            attempt_started_at=NOW - timedelta(minutes=20),
            lease_expires_at=NOW - timedelta(minutes=10),
        )
    )
    session_fixture.commit()

    response = _trigger(backup_env)

    assert response.status_code == 200
    assert notifier.sent[0][3][0][1] == stored  # exact stored bytes
    assert _rows(session_fixture)[0].status == "submitted"


def test_reclaim_is_atomic_second_caller_loses(
    backup_env, session_fixture: Session
) -> None:
    """Two retries racing a failed row: the conditional UPDATE lets exactly
    one through."""
    session_fixture.add(
        BackupRecordTable(
            backup_date=DAY1, created_at=NOW, sha256="e" * 64,
            prev_sha256=None, archive_bytes=b"{}", status="failed",
            attempt_started_at=None, lease_expires_at=None,
        )
    )
    session_fixture.commit()
    row_id = _rows(session_fixture)[0].id

    first = backup_router.try_acquire_lease(session_fixture, row_id, now=NOW)
    second = backup_router.try_acquire_lease(session_fixture, row_id, now=NOW)

    assert first is True
    assert second is False  # lease is now live; loser must not send


def test_insert_race_loser_returns_winner_state(
    backup_env, session_fixture: Session, notifier: RecordingNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reserve-then-send: the loser of the claim never emails a second archive."""
    real_find = backup_router.find_record_for_date
    calls = {"n": 0}

    def racing_find(session, day):
        # First lookup sees nothing (as the loser would); after the winner's
        # row exists the IntegrityError path re-reads truthfully.
        calls["n"] += 1
        if calls["n"] == 1 and _rows(session_fixture) == []:
            winner = BackupRecordTable(
                backup_date=day, created_at=NOW, sha256="a" * 64,
                prev_sha256=None, archive_bytes=None, status="submitted",
                attempt_started_at=None, lease_expires_at=None,
            )
            session_fixture.add(winner)
            session_fixture.commit()
            return None  # loser believes the day is unclaimed
        return real_find(session, day)

    monkeypatch.setattr(backup_router, "find_record_for_date", racing_find)

    response = _trigger(backup_env)

    assert response.status_code == 200
    assert response.json()["sha256"] == "a" * 64  # winner's state
    assert notifier.sent == []  # loser never emailed anything
    assert len(_rows(session_fixture)) == 1


# --- snapshot coherence --------------------------------------------------------


def test_snapshot_read_sees_one_database_state(tmp_path) -> None:
    """The mechanism the archive build runs under: a write committed by a
    second connection mid-transaction must not appear in reads made inside an
    open snapshot — otherwise the hashed bytes could describe a state the
    database never occupied."""
    from sqlmodel import SQLModel, create_engine, text as sql_text
    from database.schema import FamilyLink

    url = f"sqlite:///{tmp_path.as_posix()}/snap.db"
    engine_a = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine_a)
    with engine_a.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
    engine_b = create_engine(url, connect_args={"check_same_thread": False})

    with Session(engine_a) as reader:
        opened = backup_router._snapshot_begin(reader)
        assert opened is True
        before = len(reader.exec(select(FamilyLink)).all())

        # A concurrent writer commits mid-snapshot.
        with Session(engine_b) as writer:
            writer.add(FamilyLink(family_name="Interloper"))
            writer.commit()

        during = len(reader.exec(select(FamilyLink)).all())
        backup_router._snapshot_end(reader, opened)
        reader.rollback()
        after = len(reader.exec(select(FamilyLink)).all())

    assert during == before  # snapshot held
    assert after == before + 1  # write visible once the snapshot closed
    engine_a.dispose()
    engine_b.dispose()
