import logging
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from api.dependencies import (
    AuditDep,
    CurrentUser,
    NotifierDep,
    SessionDep,
    get_current_user,
    require_parent_role,
)
from core.notifications import (
    Notifier,
    override_decided_email,
    override_requested_email,
)
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
from core.ranges import ranges_overlap
from database.schema import BaselineTable, OverrideTable, UserTable

_logger = logging.getLogger(__name__)

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
        end_date=row.end_date,
        assigned_parent=ParentRole(row.assigned_parent),
        override_type=OverrideType(row.override_type),
        description=row.description,
        is_active=row.is_active,
        status=OverrideStatus(row.status),
        expires_at=row.expires_at,
        requested_by_user_id=row.requested_by_user_id,
    )


def _user(session: Session, user_id: int) -> UserTable | None:
    return session.get(UserTable, user_id)


def _other_parent(
    session: Session, family_id: int, actor_user_id: int
) -> UserTable | None:
    return session.exec(
        select(UserTable).where(
            UserTable.family_id == family_id,
            UserTable.role == "Parent",
            UserTable.id != actor_user_id,
        )
    ).first()


def _label(user: UserTable | None, fallback: str) -> str:
    if user is None or not user.custody_label:
        return fallback
    return user.custody_label


def _send_safely(notifier: Notifier, to: str, subject: str, body: str) -> None:
    """Runs in a background task. A notification is a side effect of a custody
    decision, never a precondition — no failure here may surface to the caller
    or bring down the worker."""
    try:
        notifier.send(to=to, subject=subject, body=body)
    except Exception:  # noqa: BLE001 — deliberately last-resort
        _logger.warning("Notification to %s failed", to, exc_info=True)


def _queue_email(
    background_tasks: BackgroundTasks,
    notifier: Notifier,
    *,
    to: str | None,
    subject: str,
    body: str,
) -> None:
    """Schedule a notification. The recipient address and the full message must
    already be resolved: the request-scoped DB session is closed by the time the
    background task runs, so no ORM object may cross this boundary."""
    if not to:
        return
    background_tasks.add_task(_send_safely, notifier, to, subject, body)


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
    # Exclude requests whose 24h window has closed. Without this an expired
    # request still shows as "waiting for the other parent" and the approve
    # button 410s. A read endpoint does not write, so flipping the stored status
    # stays with the decision path and the sweep endpoint below.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = session.exec(
        select(OverrideTable).where(
            OverrideTable.family_id == current_user.family_id,
            OverrideTable.status == OverrideStatus.PENDING.value,
            OverrideTable.expires_at > now,
        )
    ).all()
    return [_to_domain(row) for row in rows]


@schedule_router.post("/overrides")
def create_override(
    override: ScheduleOverride,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    notifier: NotifierDep,
    audit: AuditDep,
    current_user: Annotated[CurrentUser, Depends(require_parent_role)],
) -> ScheduleOverride:
    if override.end_date is not None and override.end_date < override.override_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be on or after override_date.",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row = OverrideTable(
        family_id=current_user.family_id,
        override_date=override.override_date,
        end_date=override.end_date,
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

    audit.append(
        family_id=current_user.family_id,
        actor_role=current_user.role,
        action_type="override_requested",
        description=f"Override {row.id} requested for {row.override_date}",
        previous_state_id=row.id,
        timestamp=now,
    )

    counterparty = _other_parent(session, current_user.family_id, current_user.id)
    subject, body = override_requested_email(
        requester_label=_label(_user(session, current_user.id), current_user.role),
        override_date=row.override_date,
        override_type=row.override_type,
        description=row.description,
        expires_at=row.expires_at,
    )
    _queue_email(
        background_tasks,
        notifier,
        to=counterparty.email if counterparty else None,
        subject=subject,
        body=body,
    )
    return _to_domain(row)


@schedule_router.post("/overrides/{override_id}/decision")
def decide_override_request(
    override_id: int,
    decision_request: OverrideDecisionRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    notifier: NotifierDep,
    audit: AuditDep,
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
        new_start = row.override_date
        new_end = row.end_date if row.end_date is not None else row.override_date
        existing_active = session.exec(
            select(OverrideTable).where(
                OverrideTable.family_id == current_user.family_id,
                OverrideTable.is_active.is_(True),
                OverrideTable.id != row.id,
            )
        ).all()
        for other in existing_active:
            other_end = (
                other.end_date if other.end_date is not None else other.override_date
            )
            if ranges_overlap(new_start, new_end, other.override_date, other_end):
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

    approved = result.new_status == OverrideStatus.APPROVED
    audit.append(
        family_id=current_user.family_id,
        actor_role=current_user.role,
        action_type="override_approved" if approved else "override_rejected",
        description=f"Override {row.id} {row.status.lower()} for {row.override_date}",
        previous_state_id=row.id,
        timestamp=now,
    )

    requester = _user(session, row.requested_by_user_id)
    subject, body = override_decided_email(
        decider_label=_label(_user(session, current_user.id), current_user.role),
        override_date=row.override_date,
        approved=approved,
    )
    _queue_email(
        background_tasks,
        notifier,
        to=requester.email if requester else None,
        subject=subject,
        body=body,
    )
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
