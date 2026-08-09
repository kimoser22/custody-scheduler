from __future__ import annotations

import logging
import os
from datetime import date

from sqlmodel import Session, select

from concierge.phones import normalize_phone
from concierge.ports import (
    Intent,
    ParsedIntent,
    RecipientOptedOutError,
    ResolvedSender,
    ScheduleQuery,
)
from core.models import OverrideType, ParentRole
from core.ranges import is_valid_range
from database.schema import UserTable

_logger = logging.getLogger(__name__)

# Twilio: "Attempt to send to unsubscribed recipient".
_OPTED_OUT_ERROR_CODE = 21610

# Openers that make a message a question about the schedule rather than a
# request to change it. A trailing "?" counts on its own.
_QUESTION_OPENERS = (
    "who", "whose", "who's", "whos", "when", "which",
    "is ", "are ", "does ", "do ", "will ", "am i", "what",
)


def _is_question(lowered: str) -> bool:
    stripped = lowered.strip()
    return stripped.endswith("?") or stripped.startswith(_QUESTION_OPENERS)


class SqlSenderResolver:
    def __init__(self, session: Session) -> None:
        self._session = session

    def resolve(self, phone: str) -> ResolvedSender | None:
        phone = normalize_phone(phone)
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
        # Last send outcome for callers that record delivery status without
        # needing transient Twilio errors to raise (webhook must stay 200).
        self.last_outcome: str = "sent"

    def send(self, to: str, body: str) -> None:
        self.sent.append((to, body))
        self.last_outcome = "sent"
        if not (self.account_sid and self.auth_token and self.from_number):
            return
        # Optional live send — require twilio package only when configured.
        import twilio.rest  # type: ignore
        from twilio.base.exceptions import TwilioException, TwilioRestException

        try:
            twilio.rest.Client(self.account_sid, self.auth_token).messages.create(
                to=to,
                from_=self.from_number,
                body=body,
            )
        except TwilioRestException as error:
            if error.code == _OPTED_OUT_ERROR_CODE:
                # Actionable rather than transient: hand it to the gateway that
                # owns the opt-out store so our list catches up with Twilio's.
                raise RecipientOptedOutError(to) from None
            self.last_outcome = "failed"
            _logger.warning(
                "SMS send to %s failed: Twilio error %s (HTTP %s)",
                to,
                error.code,
                error.status,
            )
        except (TwilioException, OSError):
            # Connection, timeout, or client misconfiguration. handle_sms has
            # already claimed this message_sid, so raising would 500 the
            # webhook and Twilio's retry would be dropped as a duplicate —
            # losing the message entirely. Log and move on instead.
            self.last_outcome = "failed"
            _logger.warning("SMS send to %s failed", to, exc_info=True)

    def send_forced(self, to: str, body: str) -> None:
        self.send(to=to, body=body)


class HeuristicIntentParser:
    """Deterministic parser for demos; swap for an LLM adapter later.

    Fails safe: returns None when the message does not clearly specify both a
    real calendar date and a target parent, rather than guessing. A wrong guess
    here silently drafts the wrong custody handoff, so ambiguity must round-trip
    to the sender as a clarification request (see concierge.nodes.parse_intent).
    """

    def parse(self, text: str) -> Intent | None:
        lowered = text.lower()

        if "parent b" in lowered:
            assigned: ParentRole | None = ParentRole.PARENT_B
        elif "parent a" in lowered:
            assigned = ParentRole.PARENT_A
        else:
            assigned = None

        # Collect every date rather than stopping at the first: a two-date
        # message is a range request, and truncating it to the start silently
        # books one day of a vacation the parent asked ten days for.
        found: list[date] = []
        for raw in text.replace(",", " ").split():
            # Trailing punctuation is normal in a question ("...on 2026-08-15?")
            # and would otherwise push the token past the 10-character check.
            token = raw.strip("?.!;:()[[]'\"")
            if len(token) == 10 and token[4] == "-" and token[7] == "-":
                try:
                    found.append(date.fromisoformat(token))
                except ValueError:
                    continue

        # A question is answered, never acted on. Checked before the swap
        # branch and regardless of whether a parent is named, because the two
        # misreadings are not symmetric: answering a swap request costs a
        # wasted text, while drafting from a question books a custody handoff
        # nobody asked for and pages the other parent about it.
        if _is_question(lowered) and found:
            start = min(found)
            end = max(found) if len(found) == 2 else None
            if len(found) > 2 or not is_valid_range(start, end):
                return None
            return ScheduleQuery(start_date=start, end_date=end)

        if assigned is None or not found:
            return None
        if len(found) > 2:
            # Which two were meant? Don't guess — ask.
            return None

        override_date = min(found)
        end_date = max(found) if len(found) == 2 else None
        if not is_valid_range(override_date, end_date):
            return None

        return ParsedIntent(
            override_date=override_date,
            end_date=end_date,
            assigned_parent=assigned,
            reason=text.strip() or "SMS swap request",
            override_type=OverrideType.MUTUAL_SWAP,
        )
