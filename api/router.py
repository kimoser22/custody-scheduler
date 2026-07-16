from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from api.dependencies import CurrentUser, SessionDep, get_current_user, require_parent_role
from core.approvals import ApprovalError, Decision, decide_override, find_expired_pending
from core.engine import calculate_schedule
from core.models import (
    BaselineSchedule,
    DailyCustodyState,
    OverrideDecisionRequest,
    OverrideStatus,
    OverrideType,
    ParentRole,
    ScheduleOverride,
)
from database.schema import BaselineTable, OverrideTable

router = APIRouter(prefix="/api/v1")
schedule_router = APIRouter(prefix="/api/v1/schedule")

DEFAULT_FAMILY_ID = 1
OVERRIDE_REQUEST_TTL = timedelta(hours=24)

DEFAULT_BASELINE = BaselineSchedule(
    epoch_start_date=date(2026, 1, 5),
    starting_parent=ParentRole.PARENT_A,
)


def _load_baseline(session: Session, family_id: int) -> BaselineSchedule:
    row = session.exec(
        select(BaselineTable).where(BaselineTable.family_id == family_id)
    ).first()
    if row is None:
        return DEFAULT_BASELINE
    return BaselineSchedule(
        epoch_start_date=row.epoch_start_date,
        starting_parent=ParentRole(row.starting_parent),
    )


def _to_domain(row: OverrideTable) -> ScheduleOverride:
    return ScheduleOverride(
        id=row.id,
        override_date=row.override_date,
        assigned_parent=ParentRole(row.assigned_parent),
        override_type=OverrideType(row.override_type),
        description=row.description,
        is_active=row.is_active,
        status=OverrideStatus(row.status),
        expires_at=row.expires_at,
        requested_by_user_id=row.requested_by_user_id,
    )


def _load_overrides(session: Session, family_id: int) -> list[ScheduleOverride]:
    rows = session.exec(
        select(OverrideTable).where(
            OverrideTable.family_id == family_id,
            OverrideTable.is_active.is_(True),
        )
    ).all()
    return [_to_domain(row) for row in rows]


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@schedule_router.get("/")
def get_schedule(
    start_date: date,
    end_date: date,
    session: SessionDep,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[DailyCustodyState]:
    baseline = _load_baseline(session, current_user.family_id)
    overrides = _load_overrides(session, current_user.family_id)
    return calculate_schedule(
        baseline=baseline,
        overrides=overrides,
        start_date=start_date,
        end_date=end_date,
    )


@schedule_router.get("/overrides/pending")
def list_pending_overrides(
    session: SessionDep,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[ScheduleOverride]:
    rows = session.exec(
        select(OverrideTable).where(
            OverrideTable.family_id == current_user.family_id,
            OverrideTable.status == OverrideStatus.PENDING.value,
        )
    ).all()
    return [_to_domain(row) for row in rows]


@schedule_router.post("/overrides")
def create_override(
    override: ScheduleOverride,
    session: SessionDep,
    current_user: Annotated[CurrentUser, Depends(require_parent_role)],
) -> ScheduleOverride:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row = OverrideTable(
        family_id=current_user.family_id,
        override_date=override.override_date,
        assigned_parent=override.assigned_parent.value,
        override_type=override.override_type.value,
        description=override.description,
        is_active=False,
        status=OverrideStatus.PENDING.value,
        requested_by_user_id=current_user.id,
        expires_at=now + OVERRIDE_REQUEST_TTL,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_domain(row)


@schedule_router.post("/overrides/{override_id}/decision")
def decide_override_request(
    override_id: int,
    decision_request: OverrideDecisionRequest,
    session: SessionDep,
    current_user: Annotated[CurrentUser, Depends(require_parent_role)],
) -> ScheduleOverride:
    row = session.get(OverrideTable, override_id)
    if row is None or row.family_id != current_user.family_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Override request not found.",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = decide_override(
        current_status=OverrideStatus(row.status),
        requested_by_user_id=row.requested_by_user_id,
        actor_user_id=current_user.id,
        decision=Decision.APPROVE if decision_request.approve else Decision.REJECT,
        now=now,
        expires_at=row.expires_at,
    )

    if result.error == ApprovalError.SELF_APPROVAL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot decide on your own override request.",
        )

    if result.error == ApprovalError.ALREADY_DECIDED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Override request has already been {row.status.lower()}.",
        )

    if result.error == ApprovalError.EXPIRED:
        row.status = OverrideStatus.EXPIRED.value
        session.add(row)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Override request has expired.",
        )

    row.status = result.new_status.value
    row.decided_by_user_id = current_user.id
    row.decided_at = now

    if result.new_status == OverrideStatus.APPROVED:
        existing_active = session.exec(
            select(OverrideTable).where(
                OverrideTable.family_id == current_user.family_id,
                OverrideTable.override_date == row.override_date,
                OverrideTable.is_active.is_(True),
                OverrideTable.id != row.id,
            )
        ).all()
        for other in existing_active:
            other.is_active = False
            session.add(other)
        row.is_active = True

    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active override for this date was just approved by another request.",
        ) from None

    session.refresh(row)
    return _to_domain(row)


@schedule_router.post("/overrides/sweep-expired")
def sweep_expired_overrides(
    session: SessionDep,
    current_user: Annotated[CurrentUser, Depends(require_parent_role)],
) -> dict[str, int]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = session.exec(
        select(OverrideTable).where(
            OverrideTable.family_id == current_user.family_id,
            OverrideTable.status == OverrideStatus.PENDING.value,
        )
    ).all()
    expired = find_expired_pending(rows, now)
    for row in expired:
        row.status = OverrideStatus.EXPIRED.value
        session.add(row)
    session.commit()
    return {"expired_count": len(expired)}
