from datetime import date

from fastapi import APIRouter

from api.dependencies import SessionDep
from core.models import CustodyDay, HolidayOverride, ScheduleRule

router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/schedule")
def get_schedule(
    start_date: date,
    end_date: date,
    session: SessionDep,
) -> list[CustodyDay]:
    ...


@router.get("/rules")
def list_rules(session: SessionDep) -> list[ScheduleRule]:
    ...


@router.post("/rules")
def create_rule(rule: ScheduleRule, session: SessionDep) -> ScheduleRule:
    ...


@router.get("/holidays")
def list_holidays(session: SessionDep) -> list[HolidayOverride]:
    ...


@router.post("/holidays")
def create_holiday(
    holiday: HolidayOverride,
    session: SessionDep,
) -> HolidayOverride:
    ...
