from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel


class ParentRole(StrEnum):
    PARENT_A = "Parent A"
    PARENT_B = "Parent B"


class OverrideType(StrEnum):
    HOLIDAY = "Holiday"
    MUTUAL_SWAP = "Mutual Swap"
    EMERGENCY = "Emergency"


class OverrideStatus(StrEnum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    EXPIRED = "Expired"


class BaselineSchedule(BaseModel):
    model_config = {"frozen": True}

    epoch_start_date: date
    starting_parent: ParentRole


class ScheduleOverride(BaseModel):
    model_config = {"frozen": True}

    id: int | None = None
    override_date: date
    assigned_parent: ParentRole
    override_type: OverrideType
    description: str
    is_active: bool = True
    status: OverrideStatus = OverrideStatus.APPROVED
    expires_at: datetime | None = None
    requested_by_user_id: int | None = None


class DailyCustodyState(BaseModel):
    model_config = {"frozen": True}

    current_date: date
    baseline_parent: ParentRole
    final_parent: ParentRole
    is_overridden: bool
    override_details: ScheduleOverride | None = None


class OverrideDecisionRequest(BaseModel):
    approve: bool
