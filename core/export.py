"""Family-of-record JSON export (archive only — no import in this module)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlmodel import Session, select

from database.schema import (
    AuditLogTable,
    BackupDeliveryTable,
    BackupRecordTable,
    BaselineTable,
    FamilyLink,
    OverrideTable,
    SmsOptOutTable,
    UserTable,
)

# v2: added backup_records / backup_deliveries history. This is the DATABASE
# export's version; the archive wrapper has its own ARCHIVE_FORMAT_VERSION
# (core/backup.py) precisely so the two can evolve independently.
EXPORT_SCHEMA_VERSION = 2


def _iso_date(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def build_family_export(session: Session, family_id: int) -> dict[str, Any]:
    """Serialize durable custody records for one family.

    Omits secrets (passcode hashes, calendar feed tokens) and ephemeral SMS
    handshake / Twilio idempotency state.
    """
    family = session.get(FamilyLink, family_id)
    family_name = family.family_name if family is not None else None

    baseline_row = session.exec(
        select(BaselineTable).where(BaselineTable.family_id == family_id)
    ).first()
    baseline = None
    if baseline_row is not None:
        baseline = {
            "epoch_start_date": _iso_date(baseline_row.epoch_start_date),
            "starting_parent": baseline_row.starting_parent,
        }

    users = session.exec(
        select(UserTable).where(UserTable.family_id == family_id).order_by(UserTable.id)
    ).all()
    user_payload = [
        {
            "id": user.id,
            "role": user.role,
            "custody_label": user.custody_label,
            "phone": user.phone,
            "email": user.email,
        }
        for user in users
    ]

    overrides = session.exec(
        select(OverrideTable)
        .where(OverrideTable.family_id == family_id)
        .order_by(OverrideTable.id)
    ).all()
    override_payload = [
        {
            "id": row.id,
            "override_date": _iso_date(row.override_date),
            "end_date": _iso_date(row.end_date),
            "assigned_parent": row.assigned_parent,
            "override_type": row.override_type,
            "description": row.description,
            "is_active": row.is_active,
            "status": row.status,
            "requested_by_user_id": row.requested_by_user_id,
            "decided_by_user_id": row.decided_by_user_id,
            "decided_at": _iso_datetime(row.decided_at),
            "expires_at": _iso_datetime(row.expires_at),
        }
        for row in overrides
    ]

    audits = session.exec(
        select(AuditLogTable)
        .where(AuditLogTable.family_id == family_id)
        .order_by(AuditLogTable.id)
    ).all()
    audit_payload = [
        {
            "id": row.id,
            "timestamp": _iso_datetime(row.timestamp),
            "actor_role": row.actor_role,
            "action_type": row.action_type,
            "description": row.description,
            "previous_state_id": row.previous_state_id,
        }
        for row in audits
    ]

    # Opt-outs are global by phone; include numbers belonging to this family's users.
    family_phones = {user.phone for user in users if user.phone}
    opt_outs = session.exec(select(SmsOptOutTable).order_by(SmsOptOutTable.phone)).all()
    opt_out_payload = [
        {
            "phone": row.phone,
            "opted_out_at": _iso_datetime(row.opted_out_at),
        }
        for row in opt_outs
        if row.phone in family_phones
    ]

    # Backup history is ordinary historical data here (the chain protocol
    # lives in the archive manifest, core/backup.py). The BLOB column is
    # deliberately excluded: archive bytes inside an archive would nest
    # cumulatively.
    backups = session.exec(
        select(BackupRecordTable).order_by(BackupRecordTable.id)
    ).all()
    backup_payload = [
        {
            "id": row.id,
            "backup_date": _iso_date(row.backup_date),
            "created_at": _iso_datetime(row.created_at),
            "sha256": row.sha256,
            "prev_sha256": row.prev_sha256,
            "status": row.status,
        }
        for row in backups
    ]
    deliveries = session.exec(
        select(BackupDeliveryTable).order_by(BackupDeliveryTable.id)
    ).all()
    delivery_payload = [
        {
            "id": row.id,
            "backup_id": row.backup_id,
            "attempt_no": row.attempt_no,
            "parent_id": row.parent_id,
            "address_used": row.address_used,
            "attempted_at": _iso_datetime(row.attempted_at),
            "outcome": row.outcome,
            "error_class": row.error_class,
        }
        for row in deliveries
    ]

    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "family_id": family_id,
        "family_name": family_name,
        "baseline": baseline,
        "users": user_payload,
        "overrides": override_payload,
        "audit_logs": audit_payload,
        "sms_opt_outs": opt_out_payload,
        "backup_records": backup_payload,
        "backup_deliveries": delivery_payload,
    }
