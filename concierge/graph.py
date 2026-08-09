from __future__ import annotations

from typing import Any, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from concierge.nodes import (
    ConciergeDeps,
    ConciergeState,
    answer_schedule_query,
    commit_transaction,
    draft_confirmation_sms,
    ingest_and_dedupe,
    notify_final_success,
    parse_intent,
    process_counterparty_reply,
    process_initiator_reply,
    send_proposal_to_counterparty,
)


def _route_after_ingest(state: ConciergeState) -> Literal["parse_intent", "end"]:
    if state.get("dropped"):
        return "end"
    return "parse_intent"


def _route_after_parse(
    state: ConciergeState,
) -> Literal["draft_confirmation_sms", "answer_schedule_query", "end"]:
    step = state.get("current_step")
    if step == "unparseable":
        return "end"
    if step == "answer_schedule_query":
        # A read: answer and stop. Never reaches the draft/handshake path.
        return "answer_schedule_query"
    return "draft_confirmation_sms"


def _route_after_initiator(
    state: ConciergeState,
) -> Literal["send_proposal_to_counterparty", "reprompt_initiator", "end"]:
    step = state.get("current_step")
    if step == "send_proposal_to_counterparty":
        return "send_proposal_to_counterparty"
    if step == "awaiting_initiator_confirm":
        # Reply wasn't YES or NO. Loop back and wait again rather than
        # deciding; the override's TTL is what ends this if nobody answers.
        return "reprompt_initiator"
    return "end"


def _route_after_counterparty(
    state: ConciergeState,
) -> Literal["commit_transaction", "reprompt_counterparty", "end"]:
    step = state.get("current_step")
    if step == "commit_transaction":
        return "commit_transaction"
    if step == "awaiting_counterparty_consent":
        return "reprompt_counterparty"
    return "end"


def _route_after_commit(
    state: ConciergeState,
) -> Literal["notify_final_success", "end"]:
    if state.get("current_step") == "notify_final_success":
        return "notify_final_success"
    return "end"


def build_concierge_graph(deps: ConciergeDeps, checkpointer: Any | None = None):
    graph = StateGraph(ConciergeState)

    def ingest_node(state: ConciergeState) -> ConciergeState:
        return ingest_and_dedupe(state, deps)

    def parse_node(state: ConciergeState) -> ConciergeState:
        return parse_intent(state, deps)

    def answer_query_node(state: ConciergeState) -> ConciergeState:
        return answer_schedule_query(state, deps)

    def draft_sms_node(state: ConciergeState) -> ConciergeState:
        updated = draft_confirmation_sms(state, deps)
        reply = interrupt({"step": updated["current_step"]})
        return {
            **updated,
            "inbound_body": str(reply),
            "current_step": "process_initiator_reply",
        }

    def initiator_node(state: ConciergeState) -> ConciergeState:
        return process_initiator_reply(state, deps)

    def propose_node(state: ConciergeState) -> ConciergeState:
        updated = send_proposal_to_counterparty(state, deps)
        reply = interrupt({"step": updated["current_step"]})
        return {
            **updated,
            "inbound_body": str(reply),
            "current_step": "process_counterparty_reply",
        }

    def counterparty_node(state: ConciergeState) -> ConciergeState:
        return process_counterparty_reply(state, deps)

    # The re-prompt SMS is already sent by the reply node; these only park the
    # conversation on the same interrupt step so the next inbound message is
    # routed back to the same reply handler.
    def reprompt_initiator_node(state: ConciergeState) -> ConciergeState:
        reply = interrupt({"step": "awaiting_initiator_confirm"})
        return {
            **state,
            "inbound_body": str(reply),
            "current_step": "process_initiator_reply",
        }

    def reprompt_counterparty_node(state: ConciergeState) -> ConciergeState:
        reply = interrupt({"step": "awaiting_counterparty_consent"})
        return {
            **state,
            "inbound_body": str(reply),
            "current_step": "process_counterparty_reply",
        }

    def commit_node(state: ConciergeState) -> ConciergeState:
        return commit_transaction(state, deps)

    def notify_node(state: ConciergeState) -> ConciergeState:
        return notify_final_success(state, deps)

    graph.add_node("ingest_and_dedupe", ingest_node)
    graph.add_node("parse_intent", parse_node)
    graph.add_node("answer_schedule_query", answer_query_node)
    graph.add_node("draft_confirmation_sms", draft_sms_node)
    graph.add_node("process_initiator_reply", initiator_node)
    graph.add_node("send_proposal_to_counterparty", propose_node)
    graph.add_node("process_counterparty_reply", counterparty_node)
    graph.add_node("reprompt_initiator", reprompt_initiator_node)
    graph.add_node("reprompt_counterparty", reprompt_counterparty_node)
    graph.add_node("commit_transaction", commit_node)
    graph.add_node("notify_final_success", notify_node)

    graph.add_edge(START, "ingest_and_dedupe")
    graph.add_conditional_edges(
        "ingest_and_dedupe",
        _route_after_ingest,
        {"parse_intent": "parse_intent", "end": END},
    )
    graph.add_conditional_edges(
        "parse_intent",
        _route_after_parse,
        {
            "draft_confirmation_sms": "draft_confirmation_sms",
            "answer_schedule_query": "answer_schedule_query",
            "end": END,
        },
    )
    graph.add_edge("answer_schedule_query", END)
    graph.add_edge("draft_confirmation_sms", "process_initiator_reply")
    graph.add_conditional_edges(
        "process_initiator_reply",
        _route_after_initiator,
        {
            "send_proposal_to_counterparty": "send_proposal_to_counterparty",
            "reprompt_initiator": "reprompt_initiator",
            "end": END,
        },
    )
    graph.add_edge("reprompt_initiator", "process_initiator_reply")
    graph.add_edge("send_proposal_to_counterparty", "process_counterparty_reply")
    graph.add_conditional_edges(
        "process_counterparty_reply",
        _route_after_counterparty,
        {
            "commit_transaction": "commit_transaction",
            "reprompt_counterparty": "reprompt_counterparty",
            "end": END,
        },
    )
    graph.add_edge("reprompt_counterparty", "process_counterparty_reply")
    graph.add_conditional_edges(
        "commit_transaction",
        _route_after_commit,
        {"notify_final_success": "notify_final_success", "end": END},
    )
    graph.add_edge("notify_final_success", END)

    return graph.compile(checkpointer=checkpointer or MemorySaver())


def resolve_thread_id(
    *,
    family_id: int | None,
    override_id: int | None,
    phone: str,
) -> str:
    if family_id is not None and override_id is not None:
        return f"family:{family_id}:override:{override_id}"
    if family_id is not None:
        return f"family:{family_id}:phone:{phone}"
    return f"phone:{phone}"
