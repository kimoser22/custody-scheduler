from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from concierge.phones import normalize_phone
from core.models import OverrideStatus, OverrideType, ParentRole, ScheduleOverride


class RecipientOptedOutError(Exception):
    """Twilio refused the send because the recipient is on *their* opt-out
    list (error 21610).

    Translated from the driver error so the gateway that owns the opt-out
    store can record it, letting our sms_opt_outs table converge on Twilio's
    without a proactive reconciliation pass.
    """

    def __init__(self, phone: str) -> None:
        super().__init__(f"Recipient {phone} has opted out of SMS.")
        self.phone = phone


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

    def send_forced(self, to: str, body: str) -> None:
        """Bypass opt-out gating (keyword ACKs). Ungated gateways alias send."""
        ...


class OptOutStore(Protocol):
    def is_opted_out(self, phone: str) -> bool: ...

    def opt_out(self, phone: str) -> None: ...

    def opt_in(self, phone: str) -> None: ...


@dataclass
class InMemoryOptOutStore:
    opted_out: set[str] = field(default_factory=set)

    def is_opted_out(self, phone: str) -> bool:
        return normalize_phone(phone) in self.opted_out

    def opt_out(self, phone: str) -> None:
        self.opted_out.add(normalize_phone(phone))

    def opt_in(self, phone: str) -> None:
        self.opted_out.discard(normalize_phone(phone))


@dataclass
class OptOutAwareSmsGateway:
    """Drops outbound SMS to opted-out numbers unless send_forced is used."""

    inner: SmsGateway
    opt_outs: OptOutStore

    def send(self, to: str, body: str) -> None:
        if self.opt_outs.is_opted_out(normalize_phone(to)):
            return
        self._send_recording_opt_outs(self.inner.send, to, body)

    def send_forced(self, to: str, body: str) -> None:
        # Keyword ACKs bypass our gate by design, but Twilio may still refuse
        # them — record that rather than letting it escape.
        self._send_recording_opt_outs(self.inner.send, to, body)

    def _send_recording_opt_outs(self, send, to: str, body: str) -> None:
        try:
            send(to=to, body=body)
        except RecipientOptedOutError:
            # Twilio's list knew something ours didn't. Catch up so the next
            # send is short-circuited here instead of rejected again.
            self.opt_outs.opt_out(to)


class IntentParser(Protocol):
    def parse(self, text: str) -> ParsedIntent | None: ...


class SenderResolver(Protocol):
    def resolve(self, phone: str) -> ResolvedSender | None: ...


class IdempotencyStore(Protocol):
    def claim(self, message_sid: str) -> bool: ...


class ThreadRegistry(Protocol):
    """Maps a phone number to the open LangGraph thread awaiting its reply."""

    def get(self, phone: str) -> str | None: ...

    def set(self, phone: str, thread_id: str) -> None: ...

    def clear(self, phone: str) -> None: ...

    def clear_by_thread(self, thread_id: str) -> None: ...


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
        end_date: date | None = None,
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

    def list_open_by_requester(
        self,
        user_id: int,
        *,
        now: datetime,
    ) -> list[ScheduleOverride]: ...


@dataclass
class FakeSmsGateway:
    sent: list[tuple[str, str]] = field(default_factory=list)

    def send(self, to: str, body: str) -> None:
        self.sent.append((to, body))

    def send_forced(self, to: str, body: str) -> None:
        self.send(to=to, body=body)


@dataclass
class FakeIntentParser:
    intent: ParsedIntent | None

    def parse(self, text: str) -> ParsedIntent | None:
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
