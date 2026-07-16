from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

from langgraph.types import Command

from concierge.graph import build_concierge_graph
from concierge.nodes import ConciergeDeps
from concierge.ports import IdempotencyStore, SenderResolver


class ConciergeRunner(Protocol):
    def handle_sms(
        self, *, message_sid: str, from_phone: str, body: str
    ) -> dict[str, Any]: ...


@dataclass
class InMemoryThreadRegistry:
    """Maps a phone number to an open LangGraph thread awaiting reply."""

    by_phone: dict[str, str] = field(default_factory=dict)

    def get(self, phone: str) -> str | None:
        return self.by_phone.get(phone)

    def set(self, phone: str, thread_id: str) -> None:
        self.by_phone[phone] = thread_id

    def clear(self, phone: str) -> None:
        self.by_phone.pop(phone, None)


@dataclass
class LangGraphConciergeRunner:
    deps: ConciergeDeps
    registry: InMemoryThreadRegistry = field(default_factory=InMemoryThreadRegistry)
    checkpointer: Any | None = None
    _graph: Any = field(init=False)

    def __post_init__(self) -> None:
        self._graph = build_concierge_graph(self.deps, checkpointer=self.checkpointer)

    def handle_sms(
        self, *, message_sid: str, from_phone: str, body: str
    ) -> dict[str, Any]:
        # Claim delivery of this exact message_sid once, before touching the
        # registry or the graph — for both a brand-new conversation and a
        # reply. A thread_id (below) is unique per conversation and never
        # reused, so invoking the graph again for an already-claimed sid —
        # whether a concurrent duplicate delivery or a delayed Twilio retry
        # arriving after the conversation already moved on to the other
        # parent — would silently start a second, unrelated conversation on
        # top of the first rather than being recognized as a duplicate.
        # Claiming here, before any invoke(), is what prevents that.
        if not self.deps.idempotency.claim(message_sid):
            return {"status": "dropped", "reason": "duplicate_message_sid"}

        open_thread = self.registry.get(from_phone)
        if open_thread:
            result = self._graph.invoke(
                Command(resume=body),
                config={"configurable": {"thread_id": open_thread}},
            )
            lang_thread_id = open_thread
        else:
            sender = self.deps.resolver.resolve(from_phone)
            if sender is None:
                return {"status": "ignored", "reason": "unknown_sender"}
            # A fresh id per conversation, never derived solely from
            # phone/family, so it can never collide with a prior or
            # concurrent conversation involving the same phone number.
            lang_thread_id = f"family:{sender.family_id}:phone:{from_phone}:{uuid4().hex[:12]}"
            result = self._graph.invoke(
                {
                    "message_sid": message_sid,
                    "inbound_from": from_phone,
                    "inbound_body": body,
                },
                config={"configurable": {"thread_id": lang_thread_id}},
            )

        if isinstance(result, dict) and result.get("dropped"):
            return {"status": "dropped", "result": result}

        interrupts = result.get("__interrupt__") if isinstance(result, dict) else None
        waiting = bool(interrupts)

        if waiting:
            # Keep LangGraph checkpoint thread id stable across resumes.
            counterparty = (
                result.get("counterparty_phone") if isinstance(result, dict) else None
            )
            step_hint = None
            if interrupts:
                first = interrupts[0]
                value = getattr(first, "value", first)
                if isinstance(value, dict):
                    step_hint = value.get("step")
            if step_hint == "awaiting_counterparty_consent" and counterparty:
                self.registry.clear(from_phone)
                self.registry.set(counterparty, lang_thread_id)
            else:
                self.registry.set(from_phone, lang_thread_id)
            return {
                "status": "waiting",
                "thread_id": lang_thread_id,
                "result": result,
            }

        if isinstance(result, dict):
            self.registry.clear(result.get("initiator_phone", ""))
            self.registry.clear(result.get("counterparty_phone", ""))
            self.registry.clear(from_phone)

        return {"status": "ok", "result": result}


@dataclass
class RecordingConciergeRunner:
    calls: list[dict[str, str]] = field(default_factory=list)
    response: dict[str, Any] = field(default_factory=lambda: {"status": "ok"})

    def handle_sms(
        self, *, message_sid: str, from_phone: str, body: str
    ) -> dict[str, Any]:
        self.calls.append(
            {"message_sid": message_sid, "from_phone": from_phone, "body": body}
        )
        return self.response
