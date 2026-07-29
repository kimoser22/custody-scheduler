"""In-flight SMS handshakes must survive a process restart.

A swap is a multi-turn conversation: request -> YES -> ACCEPT. Between turns the
graph is paused and its state lives in the checkpointer plus a phone->thread
registry. With MemorySaver both die on restart and the parents are never told,
so their next reply lands with no open thread.

The load-bearing test here is the restart proof: it drops every in-process
object between turns and resumes purely from what was written to disk.
"""

from datetime import date, datetime, timezone

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from sqlmodel import Session, SQLModel, create_engine, select

import concierge.factory as factory_module
from concierge.factory import _checkpointer_for, build_default_runner
from concierge.repos import SqlThreadRegistry
from core.models import OverrideStatus
from database.schema import FamilyLink, OverrideTable, UserTable

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)

INITIATOR = "+15550001"
COUNTERPARTY = "+15550002"


@pytest.fixture(name="file_engine")
def _file_engine(tmp_path):
    """A real on-disk SQLite database — the durable path only exists for files."""
    engine = create_engine(
        f"sqlite:///{tmp_path.as_posix()}/custody.db",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(FamilyLink(id=1, family_name="Durable Family"))
        session.add(
            UserTable(
                id=101,
                family_id=1,
                role="Parent",
                phone=INITIATOR,
                custody_label="Parent A",
            )
        )
        session.add(
            UserTable(
                id=102,
                family_id=1,
                role="Parent",
                phone=COUNTERPARTY,
                custody_label="Parent B",
            )
        )
        session.commit()
    return engine


@pytest.fixture(autouse=True)
def _clear_saver_cache():
    """Each test starts with no cached checkpointer, and leaves none behind."""
    factory_module.reset_checkpointer_cache()
    yield
    factory_module.reset_checkpointer_cache()


def _simulate_restart() -> None:
    """Drop every cached in-process object. Anything that survives this came
    off disk, which is exactly what a deploy or crash would leave behind."""
    factory_module.reset_checkpointer_cache()


# --- the restart proof --------------------------------------------------------


def test_paused_handshake_survives_a_restart(file_engine) -> None:
    with Session(file_engine) as session:
        first = build_default_runner(session=session).handle_sms(
            message_sid="SM-durable-1",
            from_phone=INITIATOR,
            body="swap 2026-07-08 to Parent B",
        )
        assert first["status"] == "waiting"

    _simulate_restart()

    with Session(file_engine) as session:
        second = build_default_runner(session=session).handle_sms(
            message_sid="SM-durable-2", from_phone=INITIATOR, body="YES"
        )
        assert second["status"] == "waiting"

    _simulate_restart()

    with Session(file_engine) as session:
        third = build_default_runner(session=session).handle_sms(
            message_sid="SM-durable-3", from_phone=COUNTERPARTY, body="ACCEPT"
        )
        assert third["status"] == "ok"

        row = session.exec(select(OverrideTable)).one()
        assert row.status == OverrideStatus.APPROVED.value
        assert row.is_active is True
        assert row.override_date == date(2026, 7, 8)


def test_registry_survives_a_restart(file_engine) -> None:
    """The phone->thread mapping is half the state; a durable checkpoint is
    useless if the reply can't be routed back to its thread."""
    with Session(file_engine) as session:
        build_default_runner(session=session).handle_sms(
            message_sid="SM-reg-1",
            from_phone=INITIATOR,
            body="swap 2026-07-08 to Parent B",
        )

    _simulate_restart()

    with Session(file_engine) as session:
        assert SqlThreadRegistry(session).get(INITIATOR) is not None


# --- SqlThreadRegistry --------------------------------------------------------


def test_registry_round_trips_through_the_database(file_engine) -> None:
    with Session(file_engine) as session:
        SqlThreadRegistry(session).set(INITIATOR, "thread-abc")

    # A separate instance on a separate session reads the persisted value.
    with Session(file_engine) as session:
        registry = SqlThreadRegistry(session)
        assert registry.get(INITIATOR) == "thread-abc"
        registry.clear(INITIATOR)

    with Session(file_engine) as session:
        assert SqlThreadRegistry(session).get(INITIATOR) is None


def test_registry_set_overwrites_an_existing_thread(file_engine) -> None:
    with Session(file_engine) as session:
        registry = SqlThreadRegistry(session)
        registry.set(INITIATOR, "thread-one")
        registry.set(INITIATOR, "thread-two")
        assert registry.get(INITIATOR) == "thread-two"


def test_registry_clear_is_safe_for_unknown_phone(file_engine) -> None:
    with Session(file_engine) as session:
        SqlThreadRegistry(session).clear("+19995550000")  # must not raise


# --- checkpointer selection ---------------------------------------------------


def test_file_backed_session_gets_a_durable_checkpointer(file_engine) -> None:
    with Session(file_engine) as session:
        assert isinstance(_checkpointer_for(session), SqliteSaver)


def test_in_memory_session_falls_back_to_memory_saver() -> None:
    """A second connection to :memory: is a *different* database, so a
    SqliteSaver there would silently persist nothing. Falling back keeps the
    rule honest: durable when the database is a file."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        assert isinstance(_checkpointer_for(session), MemorySaver)


def test_same_path_reuses_one_checkpointer(file_engine) -> None:
    """One connection per database file, shared across requests."""
    with Session(file_engine) as session:
        first = _checkpointer_for(session)
    with Session(file_engine) as session:
        assert _checkpointer_for(session) is first
