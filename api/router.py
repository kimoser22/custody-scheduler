from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from api.dependencies import CurrentUser, SessionDep, get_current_user, require_parent_role
from core.engine import calculate_schedule
from core.models import (
    BaselineSchedule,
    DailyCustodyState,
    OverrideType,
    ParentRole,
    ScheduleOverride,
)
from database.schema import BaselineTable, FamilyLink, OverrideTable

router = APIRouter(prefix="/api/v1")
schedule_router = APIRouter(prefix="/api/v1/schedule")

DEFAULT_FAMILY_ID = 1

DEFAULT_BASELINE = BaselineSchedule(
    epoch_start_date=date(2026, 1, 5),
    starting_parent=ParentRole.PARENT_A,
)


def _load_baseline(session: Session) -> BaselineSchedule:
    row = session.exec(select(BaselineTable)).first()
    if row is None:
        return DEFAULT_BASELINE
    return BaselineSchedule(
        epoch_start_date=row.epoch_start_date,
        starting_parent=ParentRole(row.starting_parent),
    )


def _load_overrides(session: Session, family_id: int) -> list[ScheduleOverride]:
    rows = session.exec(
        select(OverrideTable).where(
            OverrideTable.family_id == family_id,
            OverrideTable.is_active.is_(True),
        )
    ).all()
    return [
        ScheduleOverride(
            override_date=row.override_date,
            assigned_parent=ParentRole(row.assigned_parent),
            override_type=OverrideType(row.override_type),
            description=row.description,
            is_active=row.is_active,
        )
        for row in rows
    ]


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
    baseline = _load_baseline(session)
    overrides = _load_overrides(session, current_user.family_id)
    return calculate_schedule(
        baseline=baseline,
        overrides=overrides,
        start_date=start_date,
        end_date=end_date,
    )


@schedule_router.post("/overrides")
def create_override(
    override: ScheduleOverride,
    session: SessionDep,
    current_user: Annotated[CurrentUser, Depends(require_parent_role)],
) -> ScheduleOverride:
    existing = session.exec(
        select(OverrideTable).where(
            OverrideTable.family_id == current_user.family_id,
            OverrideTable.override_date == override.override_date,
            OverrideTable.is_active.is_(True),
        )
    ).all()
    for row in existing:
        row.is_active = False
        session.add(row)

    session.add(
        OverrideTable(
            family_id=current_user.family_id,
            override_date=override.override_date,
            assigned_parent=override.assigned_parent.value,
            override_type=override.override_type.value,
            description=override.description,
            is_active=override.is_active,
        )
    )
    session.commit()
    return override


@router.get("/rules")
def list_rules(session: SessionDep) -> list[BaselineSchedule]:
    ...


@router.post("/rules")
def create_rule(rule: BaselineSchedule, session: SessionDep) -> BaselineSchedule:
    ...


@router.get("/holidays")
def list_holidays(session: SessionDep) -> list[ScheduleOverride]:
    ...


@router.post("/holidays")
def create_holiday(
    holiday: ScheduleOverride,
    session: SessionDep,
) -> ScheduleOverride:
    ...
