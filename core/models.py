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
    DRAFT = "Draft"
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    EXPIRED = "Expired"


class NotifyStatus(StrEnum):
    """Delivery outcome for email/SMS about an override request."""

    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED_NO_ADDRESS = "skipped_no_address"
    SKIPPED_NO_PHONE = "skipped_no_phone"
    SKIPPED_OPT_OUT = "skipped_opt_out"
    UNCONFIGURED = "unconfigured"


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
    # Inclusive end of the range; None means single-day (same as override_date).
    end_date: date | None = None
    # Populated for pending-list responses; not required for engine matching.
    requested_by_label: str | None = None
    # Delivery outcomes for the counterparty ping on create (nullable legacy rows).
    email_notify_status: NotifyStatus | None = None
    sms_notify_status: NotifyStatus | None = None


class DailyCustodyState(BaseModel):
    model_config = {"frozen": True}

    current_date: date
    baseline_parent: ParentRole
    final_parent: ParentRole
    is_overridden: bool
    override_details: ScheduleOverride | None = None


class OverrideDecisionRequest(BaseModel):
    approve: bool
