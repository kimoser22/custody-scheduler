from datetime import date

from sqlmodel import Field, SQLModel


class ScheduleRuleTable(SQLModel, table=True):
    __tablename__ = "schedule_rules"

    id: int | None = Field(default=None, primary_key=True)
    start_date: date
    anchor_parent: str
    pattern_name: str = "2-2-3"


class HolidayOverrideTable(SQLModel, table=True):
    __tablename__ = "holiday_overrides"

    id: int | None = Field(default=None, primary_key=True)
    date: date
    parent: str
    reason: str | None = None
