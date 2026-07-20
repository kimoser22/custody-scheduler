from __future__ import annotations

import os
from datetime import date

from sqlmodel import Session, select

from concierge.ports import ParsedIntent, ResolvedSender
from core.models import OverrideType, ParentRole
from database.schema import UserTable


class SqlSenderResolver:
    def __init__(self, session: Session) -> None:
        self._session = session

    def resolve(self, phone: str) -> ResolvedSender | None:
        row = self._session.exec(
            select(UserTable).where(UserTable.phone == phone)
        ).first()
        if row is None or row.id is None:
            return None
        return ResolvedSender(
            user_id=row.id,
            family_id=row.family_id,
            role=row.role,
            phone=row.phone or phone,
            custody_label=row.custody_label or row.role,
        )


class EnvTwilioSmsGateway:
    """Sends via Twilio REST when credentials exist; otherwise records locally."""

    def __init__(self) -> None:
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.from_number = os.getenv("TWILIO_FROM_NUMBER")
        self.sent: list[tuple[str, str]] = []

    def send(self, to: str, body: str) -> None:
        self.sent.append((to, body))
        if not (self.account_sid and self.auth_token and self.from_number):
            return
        # Optional live send — require twilio package only when configured.
        from twilio.rest import Client  # type: ignore

        Client(self.account_sid, self.auth_token).messages.create(
            to=to,
            from_=self.from_number,
            body=body,
        )


class HeuristicIntentParser:
    """Deterministic parser for demos; swap for an LLM adapter later.

    Fails safe: returns None when the message does not clearly specify both a
    real calendar date and a target parent, rather than guessing. A wrong guess
    here silently drafts the wrong custody handoff, so ambiguity must round-trip
    to the sender as a clarification request (see concierge.nodes.parse_intent).
    """

    def parse(self, text: str) -> ParsedIntent | None:
        lowered = text.lower()

        if "parent b" in lowered:
            assigned: ParentRole | None = ParentRole.PARENT_B
        elif "parent a" in lowered:
            assigned = ParentRole.PARENT_A
        else:
            assigned = None

        override_date: date | None = None
        for token in text.replace(",", " ").split():
            if len(token) == 10 and token[4] == "-" and token[7] == "-":
                try:
                    override_date = date.fromisoformat(token)
                except ValueError:
                    continue
                break

        if override_date is None or assigned is None:
            return None

        return ParsedIntent(
            override_date=override_date,
            assigned_parent=assigned,
            reason=text.strip() or "SMS swap request",
            override_type=OverrideType.MUTUAL_SWAP,
        )
