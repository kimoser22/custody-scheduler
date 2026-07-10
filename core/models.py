from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Parent(StrEnum):
    PARENT_A = "parent_a"
    PARENT_B = "parent_b"


class CustodyDay(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: date
    parent: Parent


class ScheduleRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    start_date: date
    anchor_parent: Parent
    pattern_name: str = "2-2-3"


class HolidayOverride(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: date
    parent: Parent
    reason: str | None = None
