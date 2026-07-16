from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from core.models import OverrideStatus, OverrideType, ParentRole, ScheduleOverride


class OverrideConflictError(Exception):
    """Raised by an OverrideRepository when activating an override would
    violate the one-active-override-per-date constraint (a race with another
    approval for the same date)."""


@dataclass(frozen=True)
class ParsedIntent:
    override_date: date
    assigned_parent: ParentRole
    reason: str
    override_type: OverrideType = OverrideType.MUTUAL_SWAP


@dataclass(frozen=True)
class ResolvedSender:
    user_id: int
    family_id: int
    role: str
    phone: str
    custody_label: str


class SmsGateway(Protocol):
    def send(self, to: str, body: str) -> None: ...


class IntentParser(Protocol):
    def parse(self, text: str) -> ParsedIntent: ...


class SenderResolver(Protocol):
    def resolve(self, phone: str) -> ResolvedSender | None: ...


class IdempotencyStore(Protocol):
    def claim(self, message_sid: str) -> bool: ...


class AuditRepository(Protocol):
    def append(
        self,
        *,
        family_id: int,
        actor_role: str,
        action_type: str,
        description: str,
        previous_state_id: int | None = None,
        timestamp: datetime,
    ) -> int: ...


class OverrideRepository(Protocol):
    def create_draft(
        self,
        *,
        family_id: int,
        override_date: date,
        assigned_parent: ParentRole,
        override_type: OverrideType,
        description: str,
        requested_by_user_id: int,
        expires_at: datetime,
    ) -> ScheduleOverride: ...

    def get(self, override_id: int) -> ScheduleOverride | None: ...

    def set_status(
        self,
        override_id: int,
        status: OverrideStatus,
        *,
        is_active: bool | None = None,
        decided_by_user_id: int | None = None,
        decided_at: datetime | None = None,
    ) -> ScheduleOverride: ...

    def activate_and_supersede(
        self,
        override_id: int,
        *,
        decided_by_user_id: int,
        decided_at: datetime,
    ) -> ScheduleOverride: ...


@dataclass
class FakeSmsGateway:
    sent: list[tuple[str, str]] = field(default_factory=list)

    def send(self, to: str, body: str) -> None:
        self.sent.append((to, body))


@dataclass
class FakeIntentParser:
    intent: ParsedIntent

    def parse(self, text: str) -> ParsedIntent:
        return self.intent


@dataclass
class FakeSenderResolver:
    senders: dict[str, ResolvedSender]

    def resolve(self, phone: str) -> ResolvedSender | None:
        return self.senders.get(phone)


@dataclass
class InMemoryIdempotencyStore:
    claimed: set[str] = field(default_factory=set)

    def claim(self, message_sid: str) -> bool:
        if message_sid in self.claimed:
            return False
        self.claimed.add(message_sid)
        return True
