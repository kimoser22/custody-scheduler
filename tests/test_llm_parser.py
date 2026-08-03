"""Contract for the LLM intent-parser adapter and the composite parser.

The invariant inherited from HeuristicIntentParser carries over absolutely:
ambiguous input, API failure, refusal, or an invalid extraction must yield
None (round-trips a clarification SMS) — never a fabricated ParsedIntent,
because a wrong parse silently drafts the wrong custody handoff.

No test here touches the network: a FakeAnthropicClient stands in at the
adapter's client boundary.
"""

from dataclasses import dataclass, field
from datetime import date
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from concierge.adapters import HeuristicIntentParser
from concierge.llm_parser import CompositeIntentParser, ExtractedSwap, LLMIntentParser
from concierge.ports import FakeIntentParser, ParsedIntent
from core.models import OverrideType, ParentRole

TODAY = date(2026, 7, 29)


def _response(
    parsed_output: ExtractedSwap | None, stop_reason: str = "end_turn"
) -> SimpleNamespace:
    return SimpleNamespace(parsed_output=parsed_output, stop_reason=stop_reason)


class FakeAnthropicClient:
    """Records the kwargs of messages.parse and returns/raises a canned result."""

    def __init__(
        self, result: SimpleNamespace | None = None, error: Exception | None = None
    ) -> None:
        self._result = result
        self._error = error
        self.parse_calls: list[dict] = []
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kwargs) -> SimpleNamespace:
        self.parse_calls.append(kwargs)
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def _parser(client: FakeAnthropicClient) -> LLMIntentParser:
    return LLMIntentParser(client, model="claude-opus-4-8", today=TODAY)


def _connection_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )


def _status_error(status_code: int) -> anthropic.APIStatusError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APIStatusError(
        f"http {status_code}",
        response=httpx.Response(status_code, request=request),
        body=None,
    )


# --- LLMIntentParser contract -------------------------------------------------


def test_clear_message_yields_validated_intent() -> None:
    client = FakeAnthropicClient(
        result=_response(
            ExtractedSwap(
                override_date="2026-08-07",
                assigned_parent="Parent B",
                reason="soccer tournament",
            )
        )
    )
    intent = _parser(client).parse("swap next Friday to Parent B for soccer")
    assert intent is not None
    assert intent.override_date == date(2026, 8, 7)
    assert intent.assigned_parent == ParentRole.PARENT_B
    assert "soccer" in intent.reason.lower()
    assert intent.override_type == OverrideType.MUTUAL_SWAP


def test_null_fields_mean_unclear_and_yield_none() -> None:
    client = FakeAnthropicClient(
        result=_response(
            ExtractedSwap(override_date=None, assigned_parent=None, reason="unclear")
        )
    )
    assert _parser(client).parse("can you take them sometime?") is None


@pytest.mark.parametrize("bad_date", ["2026-13-40", "next Friday", ""])
def test_invalid_date_string_from_model_yields_none(bad_date: str) -> None:
    """The guardrail, not the schema, is the last line of defense: a
    hallucinated non-date must degrade to clarification, not crash or draft."""
    client = FakeAnthropicClient(
        result=_response(
            ExtractedSwap(
                override_date=bad_date, assigned_parent="Parent A", reason="swap"
            )
        )
    )
    assert _parser(client).parse("whatever") is None


def test_api_connection_error_yields_none() -> None:
    client = FakeAnthropicClient(error=_connection_error())
    assert _parser(client).parse("swap 2026-08-07 to Parent B") is None


@pytest.mark.parametrize("status_code", [429, 500])
def test_api_status_error_yields_none(status_code: int) -> None:
    client = FakeAnthropicClient(error=_status_error(status_code))
    assert _parser(client).parse("swap 2026-08-07 to Parent B") is None


def test_refusal_stop_reason_yields_none() -> None:
    client = FakeAnthropicClient(
        result=_response(
            ExtractedSwap(
                override_date="2026-08-07", assigned_parent="Parent B", reason="swap"
            ),
            stop_reason="refusal",
        )
    )
    assert _parser(client).parse("swap 2026-08-07 to Parent B") is None


def test_prompt_carries_today_and_both_parent_labels() -> None:
    """Relative-date phrasing only works if the model knows today's date, and
    extraction is constrained to the two real labels. Assert the contract
    without pinning prose wording."""
    client = FakeAnthropicClient(
        result=_response(
            ExtractedSwap(override_date=None, assigned_parent=None, reason="x")
        )
    )
    _parser(client).parse("swap next Friday to dad")

    assert len(client.parse_calls) == 1
    call = client.parse_calls[0]
    system = str(call.get("system", ""))
    assert TODAY.isoformat() in system
    assert "Parent A" in system
    assert "Parent B" in system
    assert call["model"] == "claude-opus-4-8"
    assert call["output_format"] is ExtractedSwap


def test_prompt_covers_multi_day_spans() -> None:
    client = FakeAnthropicClient(
        result=_response(
            ExtractedSwap(override_date=None, assigned_parent=None, reason="x")
        )
    )
    _parser(client).parse("swap next Monday through Friday to Parent B")

    system = str(client.parse_calls[0].get("system", "")).lower()
    assert "end_date" in system


# --- date ranges --------------------------------------------------------------


def test_extracted_range_becomes_a_range_intent() -> None:
    client = FakeAnthropicClient(
        result=_response(
            ExtractedSwap(
                override_date="2026-08-01",
                end_date="2026-08-10",
                assigned_parent="Parent B",
                reason="vacation",
            )
        )
    )
    intent = _parser(client).parse("swap Aug 1 through Aug 10 to Parent B")
    assert intent is not None
    assert intent.override_date == date(2026, 8, 1)
    assert intent.end_date == date(2026, 8, 10)


def test_null_end_date_means_single_day() -> None:
    client = FakeAnthropicClient(
        result=_response(
            ExtractedSwap(
                override_date="2026-08-07",
                end_date=None,
                assigned_parent="Parent B",
                reason="swap",
            )
        )
    )
    intent = _parser(client).parse("swap Aug 7 to Parent B")
    assert intent is not None
    assert intent.end_date is None


@pytest.mark.parametrize(
    "bad_end",
    ["2026-13-40", "next Friday", "", "2026-07-01"],  # last one precedes the start
)
def test_unusable_end_date_rejects_the_whole_intent(bad_end: str) -> None:
    """Never downgrade a bad range to a single-day override — that is exactly
    the silent truncation this feature exists to remove."""
    client = FakeAnthropicClient(
        result=_response(
            ExtractedSwap(
                override_date="2026-08-01",
                end_date=bad_end,
                assigned_parent="Parent B",
                reason="swap",
            )
        )
    )
    assert _parser(client).parse("whatever") is None


def test_range_longer_than_the_cap_is_rejected() -> None:
    client = FakeAnthropicClient(
        result=_response(
            ExtractedSwap(
                override_date="2026-01-01",
                end_date="2027-06-01",
                assigned_parent="Parent B",
                reason="swap",
            )
        )
    )
    assert _parser(client).parse("whatever") is None


# --- CompositeIntentParser contract -------------------------------------------


@dataclass
class SpyParser:
    intent: ParsedIntent | None
    calls: list[str] = field(default_factory=list)

    def parse(self, text: str) -> ParsedIntent | None:
        self.calls.append(text)
        return self.intent


_INTENT = ParsedIntent(
    override_date=date(2026, 8, 7),
    assigned_parent=ParentRole.PARENT_B,
    reason="swap",
)


def test_composite_skips_fallback_when_primary_parses() -> None:
    """The cost/latency guarantee: a well-formed message never hits the LLM."""
    fallback = SpyParser(intent=_INTENT)
    composite = CompositeIntentParser(FakeIntentParser(intent=_INTENT), fallback)
    assert composite.parse("swap 2026-08-07 to Parent B") == _INTENT
    assert fallback.calls == []


def test_composite_consults_fallback_when_primary_returns_none() -> None:
    fallback = SpyParser(intent=_INTENT)
    composite = CompositeIntentParser(FakeIntentParser(intent=None), fallback)
    assert composite.parse("swap next Friday to dad") == _INTENT
    assert fallback.calls == ["swap next Friday to dad"]


def test_composite_returns_none_when_both_decline() -> None:
    composite = CompositeIntentParser(
        FakeIntentParser(intent=None), SpyParser(intent=None)
    )
    assert composite.parse("???") is None


# --- Shared port contract: every IntentParser fails safe ----------------------


def _heuristic() -> "HeuristicIntentParser":
    return HeuristicIntentParser()


def _llm_declining() -> LLMIntentParser:
    """LLM parser whose model reports the message as unclear."""
    return _parser(
        FakeAnthropicClient(
            result=_response(
                ExtractedSwap(override_date=None, assigned_parent=None, reason="?")
            )
        )
    )


def _composite_declining() -> CompositeIntentParser:
    return CompositeIntentParser(_heuristic(), _llm_declining())


@pytest.mark.parametrize(
    "make_parser",
    [_heuristic, _llm_declining, _composite_declining],
    ids=["heuristic", "llm", "composite"],
)
@pytest.mark.parametrize(
    "ambiguous_text",
    [
        "can you take him sometime next week?",
        "swap 2026-08-15 please",  # no parent
        "",
    ],
)
def test_every_parser_returns_none_for_ambiguous_input(
    make_parser, ambiguous_text: str
) -> None:
    """The port-wide invariant: no IntentParser implementation may fabricate a
    ParsedIntent from an unclear message — None round-trips a clarification
    SMS instead of drafting a guessed custody handoff. Any future parser
    (new provider, new model) must be added to this parametrization."""
    assert make_parser().parse(ambiguous_text) is None
