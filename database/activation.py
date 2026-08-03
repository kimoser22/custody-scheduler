"""Single code path for activating an override and superseding overlaps.

Previously duplicated between the web decision endpoint and the SMS repo, and
therefore the place a future edit could desync the is_active flag from the
active_custody_days rows that enforce no-overlap at the database. Both callers
now funnel through activate_override, which flips flags and syncs day rows in
one unit of work.

None of these functions commit: the caller owns the transaction and the
IntegrityError translation (web -> 409, SMS -> OverrideConflictError). An
IntegrityError raised at the caller's commit is the backstop firing — a
concurrent approval claimed an overlapping day first.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlmodel import Session, delete, select

from core.models import OverrideStatus
from core.ranges import ranges_overlap
from database.schema import ActiveCustodyDayTable, OverrideTable


def _effective_end(row: OverrideTable) -> date:
    return row.end_date if row.end_date is not None else row.override_date


def _days_in_range(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def _overlapping_actives(
    session: Session,
    *,
    family_id: int,
    start: date,
    end: date,
    exclude_id: int | None,
) -> list[OverrideTable]:
    """Module-level on purpose: the deterministic race test patches this seam
    to hold both approvals at a stale read before either writes."""
    rows = session.exec(
        select(OverrideTable).where(
            OverrideTable.family_id == family_id,
            OverrideTable.is_active.is_(True),
            OverrideTable.id != exclude_id,
        )
    ).all()
    return [
        row
        for row in rows
        if ranges_overlap(start, end, row.override_date, _effective_end(row))
    ]


def deactivate_day_rows(session: Session, override_id: int) -> None:
    """Release every day the override claimed. No-op for never-active rows."""
    session.exec(
        delete(ActiveCustodyDayTable).where(
            ActiveCustodyDayTable.override_id == override_id
        )
    )


def activate_override(
    session: Session,
    row: OverrideTable,
    *,
    decided_by_user_id: int,
    decided_at: datetime,
) -> None:
    """Approve + activate `row`, superseding overlapping actives, and claim its
    days in active_custody_days. Does not commit."""
    assert row.id is not None
    start = row.override_date
    end = _effective_end(row)

    for other in _overlapping_actives(
        session, family_id=row.family_id, start=start, end=end, exclude_id=row.id
    ):
        other.is_active = False
        assert other.id is not None
        deactivate_day_rows(session, other.id)
        session.add(other)

    row.status = OverrideStatus.APPROVED.value
    row.is_active = True
    row.decided_by_user_id = decided_by_user_id
    row.decided_at = decided_at
    session.add(row)

    for day in _days_in_range(start, end):
        session.add(
            ActiveCustodyDayTable(
                family_id=row.family_id, day=day, override_id=row.id
            )
        )
