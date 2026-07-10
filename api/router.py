from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends

from api.dependencies import CurrentUser, SessionDep, get_current_user, require_parent_role
from core.models import BaselineSchedule, DailyCustodyState, ParentRole, ScheduleOverride

router = APIRouter(prefix="/api/v1")
schedule_router = APIRouter(prefix="/api/v1/schedule")


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@schedule_router.get("/")
def get_schedule(
    start_date: date,
    end_date: date,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[DailyCustodyState]:
    return [
        DailyCustodyState(
            current_date=start_date,
            baseline_parent=ParentRole.PARENT_A,
            final_parent=ParentRole.PARENT_A,
            is_overridden=False,
        )
    ]


@schedule_router.post("/overrides")
def create_override(
    override: ScheduleOverride,
    current_user: Annotated[CurrentUser, Depends(require_parent_role)],
) -> ScheduleOverride:
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
