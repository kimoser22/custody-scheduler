from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone

from langgraph.checkpoint.memory import MemorySaver
from sqlmodel import Session, select

from concierge.adapters import EnvTwilioSmsGateway, HeuristicIntentParser, SqlSenderResolver
from concierge.nodes import ConciergeDeps
from concierge.ports import IntentParser
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

_logger = logging.getLogger(__name__)


def warn_ephemeral_handshake_state(logger: logging.Logger | None = None) -> None:
    """Announce, at startup, that in-flight SMS handshakes are not durable.

    The LangGraph checkpoint (_SHARED_CHECKPOINTER) and phone->thread registry
    (_SHARED_REGISTRY) live only in this process's memory. Any restart or deploy
    drops conversations paused mid-handshake — the other parent is never told.
    Deferred tradeoff; a durable checkpointer would be needed to fix it. Until
    then, at least fail loudly instead of silently losing state.
    """
    (logger or _logger).warning(
        "SMS handshake state is in-memory only: any restart or deploy drops "
        "conversations paused mid-handshake. Run a single process and avoid "
        "restarts while handshakes are in flight."
    )


def _build_parser(today: date) -> IntentParser:
    """Heuristic-only by default; with ANTHROPIC_API_KEY set, compose the LLM
    fallback behind it (well-formed messages never cost a token; ambiguous
    ones get one bounded Claude call before falling back to clarification).
    Imported lazily so unconfigured deploys never touch the anthropic SDK."""
    heuristic = HeuristicIntentParser()
    if not os.getenv("ANTHROPIC_API_KEY"):
        return heuristic

    from concierge.llm_parser import (
        DEFAULT_MODEL,
        CompositeIntentParser,
        LLMIntentParser,
        build_anthropic_client,
    )

    llm = LLMIntentParser(
        build_anthropic_client(),
        model=os.getenv("CONCIERGE_LLM_MODEL", DEFAULT_MODEL),
        today=today,
    )
    return CompositeIntentParser(heuristic, llm)


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

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    deps = ConciergeDeps(
        sms=EnvTwilioSmsGateway(),
        parser=_build_parser(today=now.date()),
        resolver=SqlSenderResolver(session),
        overrides=SqlOverrideRepository(session),
        audit=SqlAuditRepository(session),
        idempotency=SqlIdempotencyStore(session),
        now=now,
        counterparty_by_family={},
        parents_by_family=parents_by_family,
    )
    return LangGraphConciergeRunner(
        deps=deps,
        registry=_SHARED_REGISTRY,
        checkpointer=_SHARED_CHECKPOINTER,
    )
