"""Weekly evidence-archive trigger (see core/backup.py for the invariants).

Called by a GitHub Actions cron with a dedicated bearer token. The state
machine resolves at most ONE logical archive per invocation:

1. An unresolved archive (failed, or pending with an expired lease) is retried
   first — its stored bytes resent verbatim, regardless of what the household
   calendar now says. A cron firing at 03:17 UTC is 23:17 Eastern during DST,
   so a short outage crosses household midnight; a calendar boundary has no
   integrity meaning and must never implicitly abandon an archive. On success
   the invocation STOPS — the next one may claim the current date — so a
   single retry can never land two archives in the parents' inboxes at once.
2. Already submitted today: idempotent no-op.
3. A live pending lease belongs to another in-flight process: 409.
4. Otherwise claim today: build from one snapshot, hash, INSERT pending
   (the UNIQUE backup_date arbitrates races), then send, then mark submitted.

Skipping a chain link is only ever the explicit abandon endpoint — an
auditable operator decision, never a side effect.
"""

from __future__ import annotations

import hmac
import json
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from api.dependencies import NotifierDep, SessionDep
from concierge.repos import SqlAuditRepository
from core.backup import build_archive_document, canonical_bytes, sha256_hex
from core.clock import household_today
from core.export import build_family_export
from database.schema import BackupDeliveryTable, BackupRecordTable, UserTable

backup_router = APIRouter(prefix="/api/v1/admin")

DEFAULT_FAMILY_ID = 1
LEASE_MINUTES = 10

_BEARER = "Bearer "


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _require_token(authorization: str | None) -> None:
    expected = os.getenv("BACKUP_TRIGGER_TOKEN")
    if not expected:
        # Unset means the feature is not configured; refusing loudly beats a
        # backup silently guarded by an empty string.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backup trigger is not configured.",
        )
    supplied = authorization or ""
    if supplied.startswith(_BEARER):
        supplied = supplied[len(_BEARER):]
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid backup trigger token.",
        )


def find_record_for_date(session: Session, day) -> BackupRecordTable | None:
    return session.exec(
        select(BackupRecordTable).where(BackupRecordTable.backup_date == day)
    ).first()


def _find_unresolved(session: Session) -> BackupRecordTable | None:
    """Most recent archive still owed to the parents."""
    rows = session.exec(
        select(BackupRecordTable)
        .where(BackupRecordTable.status.in_(("failed", "pending")))
        .order_by(BackupRecordTable.backup_date.desc())
    ).all()
    return rows[0] if rows else None


def try_acquire_lease(session: Session, record_id: int, *, now: datetime) -> bool:
    """Atomically take delivery ownership of a failed/expired-pending record.

    A conditional UPDATE — SQLite's single-writer model makes this race-free:
    of two concurrent re-claims, exactly one matches the WHERE clause.
    """
    from sqlalchemy import text

    result = session.connection().execute(
        text(
            "UPDATE backup_records "
            "SET status='pending', attempt_started_at=:now, lease_expires_at=:lease "
            "WHERE id=:id AND (status='failed' "
            "      OR (status='pending' AND lease_expires_at < :now))"
        ),
        {
            "id": record_id,
            "now": now.isoformat(sep=" "),
            "lease": (now + timedelta(minutes=LEASE_MINUTES)).isoformat(sep=" "),
        },
    )
    session.commit()
    return result.rowcount == 1


def _snapshot_begin(session: Session) -> bool:
    """Open a driver-level read transaction so the export reads one database
    state. pysqlite runs bare SELECTs in autocommit, so without this a write
    landing between two table reads would produce an archive that is
    cryptographically intact but describes a state that never existed.

    Returns False when a transaction is already open (which itself provides
    the snapshot)."""
    try:
        session.connection().exec_driver_sql("BEGIN")
        return True
    except Exception:  # noqa: BLE001 — "transaction within a transaction"
        return False


def _snapshot_end(session: Session, opened: bool) -> None:
    if opened:
        session.connection().exec_driver_sql("COMMIT")


def _last_submitted_sha(session: Session) -> str | None:
    rows = session.exec(
        select(BackupRecordTable)
        .where(BackupRecordTable.status == "submitted")
        .order_by(BackupRecordTable.backup_date.desc())
    ).all()
    return rows[0].sha256 if rows else None


def _next_attempt_no(session: Session, backup_id: int) -> int:
    rows = session.exec(
        select(BackupDeliveryTable).where(BackupDeliveryTable.backup_id == backup_id)
    ).all()
    return max((row.attempt_no for row in rows), default=0) + 1


def _record_summary(record: BackupRecordTable, deliveries=None) -> dict:
    return {
        "backup_date": record.backup_date.isoformat(),
        "sha256": record.sha256,
        "prev_sha256": record.prev_sha256,
        "status": record.status,
        "deliveries": [
            {
                "parent_id": d.parent_id,
                "address_used": d.address_used,
                "outcome": d.outcome,
                "attempt_no": d.attempt_no,
            }
            for d in (deliveries or [])
        ],
    }


def _deliver(
    session: Session,
    notifier,
    record: BackupRecordTable,
    *,
    now: datetime,
) -> JSONResponse:
    """Send the record's stored bytes to every required parent identity, then
    settle its status. The bytes are never rebuilt here — that is invariant 1."""
    assert record.archive_bytes is not None and record.id is not None
    raw = record.archive_bytes
    manifest = json.loads(raw.decode("utf-8"))["archive_manifest"]
    parent_ids = manifest["recipient_parent_ids"]
    backup_date = manifest["backup_date"]
    filename = f"custody-export-{backup_date}.json"
    subject = f"Custody record archive {backup_date} — sha256 {record.sha256}"
    body = (
        "Weekly custody record archive. Keep this email: it is one of the\n"
        "independent copies that make the record tamper-evident.\n\n"
        f"Archive SHA-256: {record.sha256}\n"
        f"Previous archive SHA-256: {record.prev_sha256 or '(first archive)'}\n"
    )

    attempt_no = _next_attempt_no(session, record.id)
    deliveries: list[BackupDeliveryTable] = []
    for parent_id in parent_ids:
        parent = session.get(UserTable, parent_id)
        address = parent.email if parent is not None else None
        if not address:
            outcome, error_class, used = "failed", "no_address", ""
        else:
            outcome = notifier.send_with_outcome(
                to=address,
                subject=subject,
                body=body,
                attachments=[(filename, raw)],
            )
            error_class = "smtp_failure" if outcome == "failed" else None
            used = address
        delivery = BackupDeliveryTable(
            backup_id=record.id,
            attempt_no=attempt_no,
            parent_id=parent_id,
            address_used=used,
            attempted_at=now,
            outcome=outcome,
            error_class=error_class,
        )
        deliveries.append(delivery)
        session.add(delivery)

    audit = SqlAuditRepository(session)
    if all(d.outcome == "submitted" for d in deliveries):
        # Submitted transition clears the bytes in the same commit: the
        # mailboxes are the archive of record; the BLOB was only retry state.
        record.status = "submitted"
        record.archive_bytes = None
        record.lease_expires_at = None
        session.add(record)
        audit.append(
            family_id=DEFAULT_FAMILY_ID,
            actor_role="system",
            action_type="backup_submitted",
            description=(
                f"Archive {backup_date} sha256={record.sha256} "
                f"prev={record.prev_sha256 or 'none'} submitted to "
                f"{len(deliveries)} parents"
            ),
            previous_state_id=record.id,
            timestamp=now,
        )
        session.commit()
        return JSONResponse(_record_summary(record, deliveries), status_code=200)

    record.status = "failed"
    record.lease_expires_at = now  # release ownership so a retry may re-claim
    session.add(record)
    audit.append(
        family_id=DEFAULT_FAMILY_ID,
        actor_role="system",
        action_type="backup_delivery_failed",
        description=(
            f"Archive {backup_date} sha256={record.sha256} delivery failed "
            f"({sum(1 for d in deliveries if d.outcome != 'submitted')}"
            f"/{len(deliveries)} recipients)"
        ),
        previous_state_id=record.id,
        timestamp=now,
    )
    session.commit()
    return JSONResponse(_record_summary(record, deliveries), status_code=502)


@backup_router.post("/backup-email")
def trigger_backup_email(
    session: SessionDep,
    notifier: NotifierDep,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    _require_token(authorization)
    now = _utcnow()

    # 1. An archive still owed to the parents comes first — and this
    # invocation then stops, whatever the calendar says.
    unresolved = _find_unresolved(session)
    if unresolved is not None:
        if (
            unresolved.status == "pending"
            and unresolved.lease_expires_at is not None
            and unresolved.lease_expires_at > now
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A backup attempt is already in flight.",
            )
        assert unresolved.id is not None
        if not try_acquire_lease(session, unresolved.id, now=now):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A backup attempt is already in flight.",
            )
        session.refresh(unresolved)
        return _deliver(session, notifier, unresolved, now=now)

    # 2./3. Today's state.
    today = household_today()
    existing = find_record_for_date(session, today)
    if existing is not None:
        if existing.status == "submitted":
            return JSONResponse(_record_summary(existing), status_code=200)
        # pending with a live lease (expired ones were handled above),
        # or abandoned — neither is this invocation's to touch.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Backup for {today} is {existing.status}.",
        )

    # 4. Claim today. Required identities are ALL parents; refusing to claim
    # only when nobody is reachable at all (config error, loud).
    parents = session.exec(
        select(UserTable).where(UserTable.role == "Parent").order_by(UserTable.id)
    ).all()
    if not any(parent.email for parent in parents):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No parent has an email address; backups cannot be delivered.",
        )

    opened = _snapshot_begin(session)
    try:
        payload = build_family_export(session, DEFAULT_FAMILY_ID)
        prev_sha = _last_submitted_sha(session)
    finally:
        _snapshot_end(session, opened)

    document = build_archive_document(
        backup_date=today.isoformat(),
        created_at_iso=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        prev_sha256=prev_sha,
        recipient_parent_ids=[p.id for p in parents if p.id is not None],
        data=payload,
    )
    raw = canonical_bytes(document)
    record = BackupRecordTable(
        backup_date=today,
        created_at=now,
        sha256=sha256_hex(raw),
        prev_sha256=prev_sha,
        archive_bytes=raw,
        status="pending",
        attempt_started_at=now,
        lease_expires_at=now + timedelta(minutes=LEASE_MINUTES),
    )
    session.add(record)
    try:
        session.commit()
    except IntegrityError:
        # Lost the claim race. The winner owns the day; return its state and
        # send nothing — reserve-then-send is what keeps a second archive out
        # of the parents' inboxes.
        session.rollback()
        winner = find_record_for_date(session, today)
        if winner is not None and winner.status == "submitted":
            return JSONResponse(_record_summary(winner), status_code=200)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another backup attempt claimed today first.",
        ) from None

    session.refresh(record)
    return _deliver(session, notifier, record, now=now)


@backup_router.post("/backup-abandon")
def abandon_unresolved_backup(
    session: SessionDep,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    """Explicitly skip an archive that can never complete. The ONLY way a
    chain link is skipped — auditable, never a calendar side effect."""
    _require_token(authorization)
    now = _utcnow()

    unresolved = _find_unresolved(session)
    if unresolved is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No unresolved backup to abandon.",
        )

    unresolved.status = "abandoned"
    unresolved.lease_expires_at = None
    session.add(unresolved)
    SqlAuditRepository(session).append(
        family_id=DEFAULT_FAMILY_ID,
        actor_role="system",
        action_type="backup_abandoned",
        description=(
            f"Archive {unresolved.backup_date} sha256={unresolved.sha256} "
            "abandoned by operator; the chain skips this date"
        ),
        previous_state_id=unresolved.id,
        timestamp=now,
    )
    session.commit()
    return JSONResponse(_record_summary(unresolved), status_code=200)
