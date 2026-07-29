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


def override_requested_email(
    *,
    requester_label: str,
    override_date: date,
    override_type: str,
    description: str,
    expires_at: datetime,
) -> tuple[str, str]:
    """Sent to the other parent when a swap is requested."""
    subject = f"{requester_label} requested a schedule change for {override_date}"
    body = (
        f"{requester_label} asked to change custody for {override_date}.\n\n"
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
) -> tuple[str, str]:
    """Sent to the original requester once the other parent decides."""
    outcome = "approved" if approved else "declined"
    subject = f"{decider_label} {outcome} the schedule change for {override_date}"
    if approved:
        body = (
            f"{decider_label} approved your request for {override_date}. "
            "The calendar has been updated."
        )
    else:
        body = (
            f"{decider_label} declined your request for {override_date}. "
            "The calendar is unchanged."
        )
    return subject, body
