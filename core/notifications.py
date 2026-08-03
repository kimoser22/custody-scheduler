"""Notification port and message copy.

`Notifier` mirrors `concierge.ports.SmsGateway`: a one-method delivery port so
the API layer never depends on a concrete transport. Message builders are pure
functions returning ``(subject, body)`` so copy can be asserted without any
transport at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol


class Notifier(Protocol):
    def send(self, *, to: str, subject: str, body: str) -> None: ...


@dataclass
class FakeNotifier:
    """Records messages instead of sending them (tests, local dev)."""

    sent: list[tuple[str, str, str]] = field(default_factory=list)

    def send(self, *, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))


def format_override_dates(start: date, end: date | None = None) -> str:
    if end is None or end == start:
        return str(start)
    return f"{start} to {end}"


def override_requested_email(
    *,
    requester_label: str,
    override_date: date,
    override_type: str,
    description: str,
    expires_at: datetime,
    end_date: date | None = None,
) -> tuple[str, str]:
    """Sent to the other parent when a swap is requested."""
    when = format_override_dates(override_date, end_date)
    subject = f"{requester_label} requested a schedule change for {when}"
    body = (
        f"{requester_label} asked to change custody for {when}.\n\n"
        f"Type: {override_type}\n"
        f"Reason: {description}\n\n"
        "This request needs your approval before it appears on the calendar. "
        f"It expires on {expires_at:%Y-%m-%d at %H:%M} UTC if nobody responds.\n\n"
        "Open the schedule to approve or decline."
    )
    return subject, body


def override_decided_email(
    *,
    decider_label: str,
    override_date: date,
    approved: bool,
    end_date: date | None = None,
) -> tuple[str, str]:
    """Sent to the original requester once the other parent decides."""
    when = format_override_dates(override_date, end_date)
    outcome = "approved" if approved else "declined"
    subject = f"{decider_label} {outcome} the schedule change for {when}"
    if approved:
        body = (
            f"{decider_label} approved your request for {when}. "
            "The calendar has been updated."
        )
    else:
        body = (
            f"{decider_label} declined your request for {when}. "
            "The calendar is unchanged."
        )
    return subject, body


def override_requested_sms(
    *,
    requester_label: str,
    override_date: date,
    end_date: date | None = None,
) -> str:
    """Short SMS ping when a web override is created (not a full handshake)."""
    when = format_override_dates(override_date, end_date)
    return (
        f"{requester_label} requested a schedule change for {when}. "
        "Open the schedule to approve or decline. Reply STOP to opt out."
    )
