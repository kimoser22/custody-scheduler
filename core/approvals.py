from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from core.models import OverrideStatus


class Decision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ApprovalError(StrEnum):
    ALREADY_DECIDED = "already_decided"
    EXPIRED = "expired"
    SELF_APPROVAL = "self_approval"


@dataclass(frozen=True)
class ApprovalResult:
    new_status: OverrideStatus
    error: ApprovalError | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def decide_override(
    *,
    current_status: OverrideStatus,
    requested_by_user_id: int,
    actor_user_id: int,
    decision: Decision,
    now: datetime,
    expires_at: datetime,
) -> ApprovalResult:
    if current_status != OverrideStatus.PENDING:
        return ApprovalResult(current_status, ApprovalError.ALREADY_DECIDED)

    if now >= expires_at:
        return ApprovalResult(OverrideStatus.EXPIRED, ApprovalError.EXPIRED)

    if actor_user_id == requested_by_user_id:
        return ApprovalResult(current_status, ApprovalError.SELF_APPROVAL)

    new_status = (
        OverrideStatus.APPROVED if decision == Decision.APPROVE else OverrideStatus.REJECTED
    )
    return ApprovalResult(new_status)


class ExpirableOverride(Protocol):
    status: str
    expires_at: datetime


def find_expired_pending[T: ExpirableOverride](rows: Iterable[T], now: datetime) -> list[T]:
    return [
        row
        for row in rows
        if row.status == OverrideStatus.PENDING.value and row.expires_at <= now
    ]
