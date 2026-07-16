from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from core.models import OverrideStatus


class InitiatorDecision(StrEnum):
    YES = "yes"
    NO = "no"


class HandshakeError(StrEnum):
    NOT_DRAFT = "not_draft"
    EXPIRED = "expired"


@dataclass(frozen=True)
class HandshakeResult:
    new_status: OverrideStatus
    is_active: bool = False
    error: HandshakeError | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def apply_initiator_confirm(
    *,
    current_status: OverrideStatus,
    decision: InitiatorDecision,
    now: datetime,
    expires_at: datetime,
) -> HandshakeResult:
    if current_status != OverrideStatus.DRAFT:
        return HandshakeResult(
            new_status=current_status,
            is_active=False,
            error=HandshakeError.NOT_DRAFT,
        )

    if now >= expires_at:
        return HandshakeResult(
            new_status=OverrideStatus.EXPIRED,
            is_active=False,
            error=HandshakeError.EXPIRED,
        )

    if decision == InitiatorDecision.NO:
        return HandshakeResult(
            new_status=OverrideStatus.REJECTED,
            is_active=False,
        )

    return HandshakeResult(
        new_status=OverrideStatus.PENDING,
        is_active=False,
    )
