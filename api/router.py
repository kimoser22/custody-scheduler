import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from api.dependencies import (
    AuditDep,
    CurrentUser,
    NotifierDep,
    SessionDep,
    SmsDep,
    get_current_user,
    require_parent_role,
)
from core.notifications import (
    Notifier,
    override_decided_email,
    override_requested_email,
    override_requested_sms,
)
from concierge.ports import SmsGateway
from core.approvals import ApprovalError, Decision, decide_override, find_expired_pending
from core.engine import calculate_schedule
from core.export import build_family_export
from core.ics import build_custody_ics
from core.models import (
    BaselineSchedule,
    DailyCustodyState,
    OverrideDecisionRequest,
    OverrideStatus,
    OverrideType,
    ParentRole,
    ScheduleOverride,
)
from database.activation import activate_override
from database.schema import BaselineTable, OverrideTable, UserTable

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")
schedule_router = APIRouter(prefix="/api/v1/schedule")

DEFAULT_FAMILY_ID = 1
MAX_RANGE_DAYS = 366
OVERRIDE_REQUEST_TTL = timedelta(hours=24)
PLANNED_OVERRIDE_TTL = timedelta(days=7)
FEED_PAST_DAYS = 30
FEED_FUTURE_DAYS = 180

DEFAULT_BASELINE = BaselineSchedule(
    epoch_start_date=date(2026, 1, 5),
    starting_parent=ParentRole.PARENT_A,
)


def _request_ttl(override: ScheduleOverride) -> timedelta:
    """Holiday and multi-day blocks get a week; one-day swaps stay 24h."""
    end = override.end_date if override.end_date is not None else override.override_date
    multi_day = end > override.override_date
    if override.override_type == OverrideType.HOLIDAY or multi_day:
        return PLANNED_OVERRIDE_TTL
    return OVERRIDE_REQUEST_TTL


def _date_span_label(start: date, end: date | None) -> str:
    if end is None or end == start:
        return str(start)
    return f"{start} to {end}"


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


def _to_domain(
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


def _send_sms_safely(sms: SmsGateway, to: str, body: str) -> None:
    try:
        sms.send(to=to, body=body)
    except Exception:  # noqa: BLE001 — deliberately last-resort
        _logger.warning("SMS to %s failed", to, exc_info=True)


def _queue_sms(
    background_tasks: BackgroundTasks,
    sms: SmsGateway,
    *,
    to: str | None,
    body: str,
) -> None:
    if not to:
        return
    background_tasks.add_task(_send_sms_safely, sms, to, body)


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


@schedule_router.get("/export.json")
def export_family_records(
    session: SessionDep,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Response:
    """Downloadable JSON archive of durable family custody records."""
    user = _user(session, current_user.id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    payload = build_family_export(session, user.family_id)
    body = json.dumps(payload, indent=2, sort_keys=False)
    today = datetime.now(timezone.utc).date().isoformat()
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="custody-export-{today}.json"'
            ),
            "Cache-Control": "no-store",
        },
    )


@schedule_router.get("/feed.ics")
def get_calendar_feed(
    token: str,
    session: SessionDep,
) -> Response:
    """Subscribeable ICS feed authenticated by opaque calendar_feed_token."""
    if not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing calendar feed token.",
        )
    user = session.exec(
        select(UserTable).where(UserTable.calendar_feed_token == token)
    ).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid calendar feed token.",
        )

    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=FEED_PAST_DAYS)
    end_date = today + timedelta(days=FEED_FUTURE_DAYS)
    days = calculate_schedule(
        baseline=_load_baseline(session, user.family_id),
        overrides=_load_overrides(session, user.family_id),
        start_date=start_date,
        end_date=end_date,
    )
    body = build_custody_ics(days=days, family_id=user.family_id)
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'inline; filename="custody.ics"',
            "Cache-Control": "private, max-age=300",
        },
    )


@schedule_router.get("/overrides/pending")
def list_pending_overrides(
    session: SessionDep,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[ScheduleOverride]:
    # Exclude requests whose approval window has closed. Without this an expired
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
    labels: dict[int, str] = {}
    requester_ids = {
        row.requested_by_user_id
        for row in rows
        if row.requested_by_user_id is not None
    }
    if requester_ids:
        for user in session.exec(
            select(UserTable).where(UserTable.id.in_(requester_ids))
        ).all():
            assert user.id is not None
            labels[user.id] = user.custody_label or f"user {user.id}"
    return [
        _to_domain(
            row,
            requested_by_label=(
                labels.get(row.requested_by_user_id)
                if row.requested_by_user_id is not None
                else None
            ),
        )
        for row in rows
    ]


@schedule_router.post("/overrides")
def create_override(
    override: ScheduleOverride,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    notifier: NotifierDep,
    sms: SmsDep,
    audit: AuditDep,
    current_user: Annotated[CurrentUser, Depends(require_parent_role)],
) -> ScheduleOverride:
    if override.end_date is not None and override.end_date < override.override_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be on or after override_date.",
        )
    if (
        override.end_date is not None
        and (override.end_date - override.override_date).days > MAX_RANGE_DAYS
    ):
        # Activation writes one active_custody_days row per day; a typo'd
        # far-future end date should fail here, not at approval.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Override range cannot exceed {MAX_RANGE_DAYS} days.",
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
        expires_at=now + _request_ttl(override),
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    date_label = _date_span_label(row.override_date, row.end_date)
    audit.append(
        family_id=current_user.family_id,
        actor_role=current_user.role,
        action_type="override_requested",
        description=f"Override {row.id} requested for {date_label}",
        previous_state_id=row.id,
        timestamp=now,
    )

    counterparty = _other_parent(session, current_user.family_id, current_user.id)
    requester_label = _label(_user(session, current_user.id), current_user.role)
    subject, body = override_requested_email(
        requester_label=requester_label,
        override_date=row.override_date,
        end_date=row.end_date,
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

    # Opt-out suppression is enforced by the gateway itself (see
    # api.dependencies.get_sms_gateway), so no check is needed here.
    _queue_sms(
        background_tasks,
        sms,
        to=counterparty.phone if counterparty else None,
        body=override_requested_sms(
            requester_label=requester_label,
            override_date=row.override_date,
            end_date=row.end_date,
        ),
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

    if result.new_status == OverrideStatus.APPROVED:
        # Shared with the SMS path (database/activation.py): flips flags and
        # syncs active_custody_days in one unit of work.
        activate_override(
            session, row, decided_by_user_id=current_user.id, decided_at=now
        )
    else:
        row.status = result.new_status.value
        row.decided_by_user_id = current_user.id
        row.decided_at = now
        session.add(row)

    try:
        session.commit()
    except IntegrityError:
        # The active_custody_days backstop fired: a concurrent approval claimed
        # an overlapping day between our read and this commit.
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflicts with an override that was just approved by another request.",
        ) from None

    session.refresh(row)

    approved = result.new_status == OverrideStatus.APPROVED
    date_label = _date_span_label(row.override_date, row.end_date)
    audit.append(
        family_id=current_user.family_id,
        actor_role=current_user.role,
        action_type="override_approved" if approved else "override_rejected",
        description=f"Override {row.id} {row.status.lower()} for {date_label}",
        previous_state_id=row.id,
        timestamp=now,
    )

    requester = _user(session, row.requested_by_user_id)
    subject, body = override_decided_email(
        decider_label=_label(_user(session, current_user.id), current_user.role),
        override_date=row.override_date,
        end_date=row.end_date,
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
