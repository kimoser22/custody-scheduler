from __future__ import annotations

import logging
import os
import sqlite3
from datetime import date, datetime, timezone
from typing import Any
from weakref import WeakKeyDictionary

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from sqlmodel import Session, select

from concierge.adapters import EnvTwilioSmsGateway, HeuristicIntentParser, SqlSenderResolver
from concierge.nodes import ConciergeDeps
from concierge.ports import IntentParser, OptOutAwareSmsGateway
from concierge.repos import (
    SqlAuditRepository,
    SqlIdempotencyStore,
    SqlOptOutStore,
    SqlOverrideRepository,
    SqlThreadRegistry,
)
from concierge.runner import LangGraphConciergeRunner
from database.connection import engine, resolve_database_url
from database.schema import UserTable

# One SqliteSaver per database file, shared across requests in this process.
# The saved state itself lives on disk, so this is a connection cache rather
# than the state — a restart rebuilds it and reads the same checkpoints back.
_SQLITE_SAVERS: dict[str, SqliteSaver] = {}

# Ephemeral databases keep the pre-durability behavior: one MemorySaver per
# engine, shared across builds within the process. Keyed weakly so throwaway
# test engines are collected with their saver.
_MEMORY_SAVERS: WeakKeyDictionary[Any, MemorySaver] = WeakKeyDictionary()

_logger = logging.getLogger(__name__)


def reset_checkpointer_cache() -> None:
    """Drop cached connections. Tests use this to simulate a process restart:
    anything that survives it came off disk."""
    for saver in _SQLITE_SAVERS.values():
        try:
            saver.conn.close()
        except Exception:  # noqa: BLE001 — best-effort teardown
            pass
    _SQLITE_SAVERS.clear()
    _MEMORY_SAVERS.clear()


def _shared_sqlite_saver(path: str) -> SqliteSaver:
    saver = _SQLITE_SAVERS.get(path)
    if saver is None:
        # check_same_thread=False: FastAPI runs these sync endpoints in a
        # threadpool. SqliteSaver serializes its own writes with a lock.
        connection = sqlite3.connect(path, check_same_thread=False)
        # WAL so a checkpoint write doesn't block a concurrent read.
        connection.execute("PRAGMA journal_mode=WAL")
        saver = SqliteSaver(connection)
        saver.setup()
        _SQLITE_SAVERS[path] = saver
    return saver


def _checkpointer_for(session: Session) -> Any:
    """Durable when the session's database is a file; in-process when it isn't.

    A second connection to ':memory:' opens a *different* database, so a
    SqliteSaver there would silently persist nothing — falling back keeps the
    rule honest rather than pretending to be durable.
    """
    bind = session.get_bind()
    database = bind.url.database
    if not database or database == ":memory:":
        saver = _MEMORY_SAVERS.get(bind)
        if saver is None:
            saver = MemorySaver()
            _MEMORY_SAVERS[bind] = saver
        return saver
    return _shared_sqlite_saver(database)


def describe_handshake_durability(logger: logging.Logger | None = None) -> None:
    """State at startup where in-flight handshakes are kept.

    Paused conversations are checkpointed to the database, so a restart or
    deploy no longer drops them. Warn only when the database is ephemeral, in
    which case the old in-memory caveat still applies.
    """
    log = logger or _logger
    database = resolve_database_url()
    if ":memory:" in database:
        log.warning(
            "SMS handshake state is in-memory only: any restart drops "
            "conversations paused mid-handshake."
        )
        return
    # WARNING (not INFO): uvicorn's default config hides application INFO logs,
    # so operators never saw the durable confirmation on Fly.
    log.warning(
        "SMS handshake state is durable: checkpointed to %s and survives restarts.",
        database,
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
    opt_outs = SqlOptOutStore(session)
    deps = ConciergeDeps(
        sms=OptOutAwareSmsGateway(EnvTwilioSmsGateway(), opt_outs),
        parser=_build_parser(today=now.date()),
        resolver=SqlSenderResolver(session),
        overrides=SqlOverrideRepository(session),
        audit=SqlAuditRepository(session),
        idempotency=SqlIdempotencyStore(session),
        now=now,
        counterparty_by_family={},
        parents_by_family=parents_by_family,
        opt_outs=opt_outs,
    )
    return LangGraphConciergeRunner(
        deps=deps,
        registry=SqlThreadRegistry(session),
        checkpointer=_checkpointer_for(session),
    )
