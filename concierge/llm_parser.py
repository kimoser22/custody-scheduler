"""LLM-backed intent parsing behind the IntentParser port.

LLMIntentParser extracts a swap request via Claude structured outputs;
CompositeIntentParser tries the free deterministic heuristic first and
consults the LLM only when it declines. Both preserve the port's fail-safe
contract: anything short of a fully-validated extraction returns None (the
concierge then asks for clarification) — a wrong guess here silently drafts
the wrong custody handoff, so no layer is allowed to guess.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Protocol

import anthropic
from pydantic import BaseModel

from concierge.ports import IntentParser, ParsedIntent
from core.models import OverrideType, ParentRole

DEFAULT_MODEL = "claude-opus-4-8"

# Twilio abandons webhooks after ~15s; a slow parse must degrade to the
# clarification path rather than hang the webhook, so no retries and a
# timeout well inside that budget.
CLIENT_TIMEOUT_SECONDS = 8.0

_PARENT_ROLES = {
    "Parent A": ParentRole.PARENT_A,
    "Parent B": ParentRole.PARENT_B,
}


class ExtractedSwap(BaseModel):
    """What the model must return. Nullable fields are the schema-level escape
    hatch: the system prompt instructs the model to return null rather than
    guess. override_date stays a string so a hallucinated non-date fails our
    own validation (-> None) instead of crashing schema parsing."""

    override_date: str | None
    assigned_parent: Literal["Parent A", "Parent B"] | None
    reason: str


class _ParsingClient(Protocol):
    """The slice of anthropic.Anthropic the adapter uses (fakeable in tests)."""

    @property
    def messages(self): ...  # noqa: E704 — structural typing only


def _system_prompt(today: date) -> str:
    return (
        "You extract custody-swap requests from SMS messages for a household "
        "scheduling app. Today's date is "
        f"{today.isoformat()}. The only valid parents are exactly "
        '"Parent A" and "Parent B" (map nicknames like mom/dad only when the '
        "message makes the mapping unambiguous).\n"
        "Return the requested calendar date as an ISO YYYY-MM-DD string, "
        "resolving relative phrases like 'next Friday' against today's date.\n"
        "If the message does not clearly specify BOTH a real calendar date "
        "AND one of the two parents, return null for those fields — never "
        "guess. A wrong extraction schedules a wrong custody handoff."
    )


class LLMIntentParser:
    """Claude-backed IntentParser. Fails safe: API errors, refusals, missing
    fields, and invalid dates all yield None."""

    def __init__(
        self,
        client: _ParsingClient,
        *,
        model: str = DEFAULT_MODEL,
        today: date,
    ) -> None:
        self._client = client
        self.model = model
        self._today = today

    def parse(self, text: str) -> ParsedIntent | None:
        try:
            response = self._client.messages.parse(
                model=self.model,
                max_tokens=1024,
                system=_system_prompt(self._today),
                messages=[{"role": "user", "content": text}],
                output_format=ExtractedSwap,
            )
        except anthropic.APIError:
            # Connection failures, timeouts, 4xx/5xx alike: degrade to the
            # clarification path; the webhook must never 500 over parsing.
            return None

        if getattr(response, "stop_reason", None) == "refusal":
            return None

        extracted = getattr(response, "parsed_output", None)
        if (
            extracted is None
            or extracted.override_date is None
            or extracted.assigned_parent is None
        ):
            return None

        try:
            override_date = date.fromisoformat(extracted.override_date)
        except ValueError:
            return None

        assigned = _PARENT_ROLES.get(extracted.assigned_parent)
        if assigned is None:
            return None

        reason = extracted.reason.strip() or text.strip() or "SMS swap request"
        return ParsedIntent(
            override_date=override_date,
            assigned_parent=assigned,
            reason=reason,
            override_type=OverrideType.MUTUAL_SWAP,
        )


class CompositeIntentParser:
    """Heuristic-first combinator: the deterministic primary handles
    well-formed messages for free; the fallback (LLM) is consulted only when
    the primary declines. None from both means genuinely unclear."""

    def __init__(self, primary: IntentParser, fallback: IntentParser) -> None:
        self.primary = primary
        self.fallback = fallback

    def parse(self, text: str) -> ParsedIntent | None:
        intent = self.primary.parse(text)
        if intent is not None:
            return intent
        return self.fallback.parse(text)


def build_anthropic_client() -> anthropic.Anthropic:
    """Sync client tuned for the webhook path (bounded latency, no retries)."""
    return anthropic.Anthropic(timeout=CLIENT_TIMEOUT_SECONDS, max_retries=0)
