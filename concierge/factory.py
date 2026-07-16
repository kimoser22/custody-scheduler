from __future__ import annotations

from datetime import datetime, timezone

from langgraph.checkpoint.memory import MemorySaver
from sqlmodel import Session, select

from concierge.adapters import EnvTwilioSmsGateway, HeuristicIntentParser, SqlSenderResolver
from concierge.nodes import ConciergeDeps
from concierge.repos import SqlAuditRepository, SqlIdempotencyStore, SqlOverrideRepository
from concierge.runner import InMemoryThreadRegistry, LangGraphConciergeRunner
from database.connection import engine
from database.schema import UserTable

# Shared across every build_default_runner() call within this process so that
# a paused (interrupted) handshake survives between separate webhook requests.
# Each request gets a fresh ConciergeDeps (DB session, "now"), but the
# LangGraph checkpoint state and the phone->thread mapping persist here.
_SHARED_CHECKPOINTER = MemorySaver()
_SHARED_REGISTRY = InMemoryThreadRegistry()


def build_default_runner(session: Session | None = None) -> LangGraphConciergeRunner:
    session = session or Session(engine)

    users = session.exec(select(UserTable).where(UserTable.role == "Parent")).all()
    parents_by_family: dict[int, list[tuple[int, str, str]]] = {}
    for user in users:
        if user.id is None or not user.phone:
            continue
        parents_by_family.setdefault(user.family_id, []).append(
            (user.id, user.phone, user.custody_label or "Parent")
        )

    deps = ConciergeDeps(
        sms=EnvTwilioSmsGateway(),
        parser=HeuristicIntentParser(),
        resolver=SqlSenderResolver(session),
        overrides=SqlOverrideRepository(session),
        audit=SqlAuditRepository(session),
        idempotency=SqlIdempotencyStore(session),
        now=datetime.now(timezone.utc).replace(tzinfo=None),
        counterparty_by_family={},
        parents_by_family=parents_by_family,
    )
    return LangGraphConciergeRunner(
        deps=deps,
        registry=_SHARED_REGISTRY,
        checkpointer=_SHARED_CHECKPOINTER,
    )
