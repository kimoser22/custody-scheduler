"""Loading the inputs `calculate_schedule` needs, in one place.

These used to be private helpers inside api/router.py. They moved here when the
SMS concierge learned to answer "who has the kids on X?": if the two surfaces
loaded the baseline or the override set differently, a parent could get one
answer by text and a different one in the app on the same day. Sharing the
loaders is what makes that impossible rather than merely unlikely.
"""

from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from core.models import (
    BaselineSchedule,
    NotifyStatus,
    OverrideStatus,
    OverrideType,
    ParentRole,
    ScheduleOverride,
)
from database.schema import BaselineTable, OverrideTable

DEFAULT_BASELINE = BaselineSchedule(
    epoch_start_date=date(2026, 1, 5),
    starting_parent=ParentRole.PARENT_A,
)


def load_baseline(session: Session, family_id: int) -> BaselineSchedule:
    row = session.exec(
        select(BaselineTable).where(BaselineTable.family_id == family_id)
    ).first()
    if row is None:
        return DEFAULT_BASELINE
    return BaselineSchedule(
        epoch_start_date=row.epoch_start_date,
        starting_parent=ParentRole(row.starting_parent),
    )


def override_to_domain(
    row: OverrideTable,
    *,
    requested_by_label: str | None = None,
) -> ScheduleOverride:
    return ScheduleOverride(
        id=row.id,
        override_date=row.override_date,
        end_date=row.end_date,
        assigned_parent=ParentRole(row.assigned_parent),
        override_type=OverrideType(row.override_type),
        description=row.description,
        is_active=row.is_active,
        status=OverrideStatus(row.status),
        expires_at=row.expires_at,
        requested_by_user_id=row.requested_by_user_id,
        requested_by_label=requested_by_label,
        email_notify_status=(
            NotifyStatus(row.email_notify_status)
            if row.email_notify_status
            else None
        ),
        sms_notify_status=(
            NotifyStatus(row.sms_notify_status) if row.sms_notify_status else None
        ),
    )


def load_overrides(session: Session, family_id: int) -> list[ScheduleOverride]:
    rows = session.exec(
        select(OverrideTable).where(
            OverrideTable.family_id == family_id,
            OverrideTable.is_active.is_(True),
        )
    ).all()
    return [override_to_domain(row) for row in rows]
