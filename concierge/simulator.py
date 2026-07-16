"""Terminal simulator for the LangGraph double-handshake (no Twilio required).

Run:
  .\\.venv\\Scripts\\python.exe -m concierge.simulator
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from langgraph.types import Command
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from concierge.adapters import HeuristicIntentParser
from concierge.graph import build_concierge_graph
from concierge.nodes import ConciergeDeps
from concierge.ports import (
    FakeSenderResolver,
    FakeSmsGateway,
    InMemoryIdempotencyStore,
    ResolvedSender,
)
from concierge.repos import SqlAuditRepository, SqlOverrideRepository
from database import schema  # noqa: F401 — register ORM tables
from database.schema import FamilyLink


THREAD_ID = "sim-1"
INITIATOR_PHONE = "+15550001"
COUNTERPARTY_PHONE = "+15550002"


def _interrupt_payload(result: dict[str, Any]) -> Any:
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    first = interrupts[0]
    return getattr(first, "value", first)


def is_interrupted(result: dict[str, Any]) -> bool:
    return bool(result.get("__interrupt__"))


def build_simulator_stack() -> tuple[Any, ConciergeDeps, FakeSmsGateway, Session]:
    """In-memory SQLite + fakes, same pattern as concierge graph tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(FamilyLink(id=1, family_name="Simulator Family"))
    session.commit()

    sms = FakeSmsGateway()
    deps = ConciergeDeps(
        sms=sms,
        parser=HeuristicIntentParser(),
        resolver=FakeSenderResolver(
            {
                INITIATOR_PHONE: ResolvedSender(
                    user_id=101,
                    family_id=1,
                    role="Parent",
                    phone=INITIATOR_PHONE,
                    custody_label="Parent A",
                ),
                COUNTERPARTY_PHONE: ResolvedSender(
                    user_id=102,
                    family_id=1,
                    role="Parent",
                    phone=COUNTERPARTY_PHONE,
                    custody_label="Parent B",
                ),
            }
        ),
        overrides=SqlOverrideRepository(session),
        audit=SqlAuditRepository(session),
        idempotency=InMemoryIdempotencyStore(),
        now=datetime.now(timezone.utc).replace(tzinfo=None),
        counterparty_by_family={1: (102, COUNTERPARTY_PHONE, "Parent B")},
        parents_by_family={
            1: [
                (101, INITIATOR_PHONE, "Parent A"),
                (102, COUNTERPARTY_PHONE, "Parent B"),
            ]
        },
    )
    graph = build_concierge_graph(deps)
    return graph, deps, sms, session


def run_until_complete(
    graph: Any,
    *,
    initial_state: dict[str, Any],
    resumes: list[str],
    thread_id: str = THREAD_ID,
) -> dict[str, Any]:
    """Drive invoke → resume loop with scripted replies (used by tests + CLI)."""
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(initial_state, config=config)
    resume_iter = iter(resumes)
    while is_interrupted(result):
        try:
            reply = next(resume_iter)
        except StopIteration as exc:
            raise RuntimeError(
                "Graph still interrupted but no more scripted resumes were provided."
            ) from exc
        result = graph.invoke(Command(resume=reply), config=config)
    return result


def _print_sms_log(sms: FakeSmsGateway) -> None:
    print("\n--- SMS log (FakeSmsGateway) ---")
    if not sms.sent:
        print("(none)")
        return
    for to, body in sms.sent:
        print(f"TO {to}")
        print(f"  {body}")
        print()


def _print_interrupt_and_latest_sms(result: dict[str, Any], sms: FakeSmsGateway) -> None:
    payload = _interrupt_payload(result)
    print("\n=== Graph paused (interrupt) ===")
    if payload is not None:
        print(f"interrupt: {payload}")
    if sms.sent:
        to, body = sms.sent[-1]
        print(f"\nLatest outbound SMS -> {to}:")
        print(body)
    print("\nReply as if by SMS (YES/NO or ACCEPT/DENY).")


def main() -> None:
    print("Custody Scheduler — LangGraph double-handshake simulator")
    print(f"Initiator phone: {INITIATOR_PHONE} (Parent A)")
    print(f"Counterparty:    {COUNTERPARTY_PHONE} (Parent B)")
    print("No Twilio required. Type 'quit' to exit.\n")

    graph, deps, sms, session = build_simulator_stack()
    config = {"configurable": {"thread_id": THREAD_ID}}

    try:
        initial = input(
            "Initial SMS from Parent A "
            "(e.g. 'swap 2026-07-08 to Parent B for trains')\n> "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        session.close()
        return

    if not initial or initial.lower() in {"quit", "exit", "q"}:
        print("Cancelled.")
        session.close()
        return

    result = graph.invoke(
        {
            "message_sid": f"SM-sim-{uuid.uuid4().hex[:12]}",
            "inbound_from": INITIATOR_PHONE,
            "inbound_body": initial,
        },
        config=config,
    )

    if result.get("dropped"):
        print("Message dropped:", result.get("error") or result.get("current_step"))
        _print_sms_log(sms)
        session.close()
        return

    while is_interrupted(result):
        _print_interrupt_and_latest_sms(result, sms)
        try:
            reply = input("SMS reply> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            session.close()
            return
        if reply.lower() in {"quit", "exit", "q"}:
            print("Cancelled.")
            session.close()
            return
        result = graph.invoke(Command(resume=reply), config=config)

    print("\n=== Flow complete ===")
    print(f"current_step: {result.get('current_step')}")
    override_id = result.get("override_id")
    if override_id is not None:
        override = deps.overrides.get(override_id)
        if override is not None:
            print(
                f"override #{override.id}: status={override.status.value} "
                f"is_active={override.is_active} "
                f"date={override.override_date} "
                f"parent={override.assigned_parent.value}"
            )
    _print_sms_log(sms)
    session.close()


if __name__ == "__main__":
    main()
