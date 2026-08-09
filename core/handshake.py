from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from core.approvals import Decision
from core.models import OverrideStatus


class InitiatorDecision(StrEnum):
    YES = "yes"
    NO = "no"


# Replies are matched against explicit vocabularies, and anything outside them
# means "no answer yet" rather than "no". Treating an unrecognized reply as a
# refusal is how a parent asking a question mid-handshake used to lose their
# request without being told.
_INITIATOR_YES = frozenset({"yes", "y", "yeah", "yep", "ok", "okay", "confirm", "sure"})
_INITIATOR_NO = frozenset({"no", "n", "nope", "cancel", "stop request"})
_COUNTERPARTY_APPROVE = frozenset({"accept", "yes", "y", "ok", "okay", "approve"})
_COUNTERPARTY_REJECT = frozenset({"deny", "no", "n", "nope", "reject", "decline"})


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split()).rstrip(".!?")


def parse_initiator_reply(text: str) -> InitiatorDecision | None:
    """YES/NO from the requester, or None when the reply is not an answer."""
    token = _normalize(text)
    if token in _INITIATOR_YES:
        return InitiatorDecision.YES
    if token in _INITIATOR_NO:
        return InitiatorDecision.NO
    return None


def parse_counterparty_reply(text: str) -> Decision | None:
    """ACCEPT/DENY from the other parent, or None when it is not an answer."""
    token = _normalize(text)
    if token in _COUNTERPARTY_APPROVE:
        return Decision.APPROVE
    if token in _COUNTERPARTY_REJECT:
        return Decision.REJECT
    return None


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
