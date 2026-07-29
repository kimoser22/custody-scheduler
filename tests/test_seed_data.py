"""Idempotent seeding contract for ensure_default_seed_data.

Contract (back-fill NULLs only): a fresh DB seeds the family, baseline, and the
three demo users; re-running inserts any missing seed user and back-fills a
NULL passcode_hash from its env var, but never overwrites a hash that is already
set and never duplicates rows.
"""

from collections.abc import Generator

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from api.passcodes import hash_passcode, verify_passcode
from api.router import DEFAULT_FAMILY_ID
from database import schema  # noqa: F401 — register ORM tables on metadata
from database.schema import BaselineTable, FamilyLink, UserTable
from main import ensure_default_seed_data

_PASSCODE_ENV_VARS = (
    "SEED_PARENT_A_PASSCODE",
    "SEED_PARENT_B_PASSCODE",
    "SEED_VIEWER_PASSCODE",
)


@pytest.fixture(name="seed_session")
def _seed_session() -> Generator[Session, None, None]:
    """A fresh in-memory DB with the tables created but NOT pre-seeded — seeding
    itself must create the family, so unlike conftest we add nothing here."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _clear_seed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test from a known-empty passcode env; tests opt back in."""
    for var in _PASSCODE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _user(session: Session, user_id: int) -> UserTable | None:
    return session.get(UserTable, user_id)


def test_empty_db_with_env_seeds_family_baseline_and_users(
    seed_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SEED_PARENT_A_PASSCODE", "alpha")
    monkeypatch.setenv("SEED_PARENT_B_PASSCODE", "bravo")
    monkeypatch.setenv("SEED_VIEWER_PASSCODE", "look")

    ensure_default_seed_data(seed_session)

    assert seed_session.get(FamilyLink, DEFAULT_FAMILY_ID) is not None
    assert (
        seed_session.exec(
            select(BaselineTable).where(
                BaselineTable.family_id == DEFAULT_FAMILY_ID
            )
        ).first()
        is not None
    )

    parent_a = _user(seed_session, 101)
    parent_b = _user(seed_session, 102)
    viewer = _user(seed_session, 2)
    assert parent_a is not None and parent_a.role == "Parent"
    assert parent_b is not None and parent_b.role == "Parent"
    assert viewer is not None and viewer.role == "Viewer"
    assert verify_passcode("alpha", parent_a.passcode_hash)
    assert verify_passcode("bravo", parent_b.passcode_hash)
    assert verify_passcode("look", viewer.passcode_hash)


def test_empty_db_without_env_seeds_null_passcodes(seed_session: Session) -> None:
    ensure_default_seed_data(seed_session)

    for user_id in (101, 102, 2):
        user = _user(seed_session, user_id)
        assert user is not None
        assert user.passcode_hash is None


def test_repeated_calls_do_not_duplicate_rows(
    seed_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SEED_PARENT_A_PASSCODE", "alpha")

    ensure_default_seed_data(seed_session)
    ensure_default_seed_data(seed_session)

    assert len(seed_session.exec(select(FamilyLink)).all()) == 1
    assert len(seed_session.exec(select(BaselineTable)).all()) == 1
    assert len(seed_session.exec(select(UserTable)).all()) == 3


def test_backfills_null_passcode_when_env_becomes_set(
    seed_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # First boot: Parent A has no passcode configured -> hash is NULL.
    ensure_default_seed_data(seed_session)
    assert _user(seed_session, 101).passcode_hash is None

    # Operator later sets the secret; next boot back-fills it.
    monkeypatch.setenv("SEED_PARENT_A_PASSCODE", "alpha")
    ensure_default_seed_data(seed_session)

    parent_a = _user(seed_session, 101)
    assert parent_a.passcode_hash is not None
    assert verify_passcode("alpha", parent_a.passcode_hash)


def test_does_not_overwrite_an_existing_passcode(
    seed_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SEED_PARENT_A_PASSCODE", "old")
    ensure_default_seed_data(seed_session)

    # A changed secret must NOT silently rotate the stored hash on boot.
    monkeypatch.setenv("SEED_PARENT_A_PASSCODE", "new")
    ensure_default_seed_data(seed_session)

    parent_a = _user(seed_session, 101)
    assert verify_passcode("old", parent_a.passcode_hash)
    assert not verify_passcode("new", parent_a.passcode_hash)


def test_inserts_a_missing_seed_user_on_existing_db(
    seed_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Simulate a DB seeded before the Viewer entry existed: only the parents.
    seed_session.add(FamilyLink(id=DEFAULT_FAMILY_ID, family_name="Default Family"))
    seed_session.add(
        UserTable(
            id=101,
            family_id=DEFAULT_FAMILY_ID,
            role="Parent",
            passcode_hash=hash_passcode("alpha"),
        )
    )
    seed_session.add(
        UserTable(
            id=102,
            family_id=DEFAULT_FAMILY_ID,
            role="Parent",
            passcode_hash=hash_passcode("bravo"),
        )
    )
    seed_session.commit()

    monkeypatch.setenv("SEED_VIEWER_PASSCODE", "look")
    ensure_default_seed_data(seed_session)

    viewer = _user(seed_session, 2)
    assert viewer is not None and viewer.role == "Viewer"
    assert verify_passcode("look", viewer.passcode_hash)
    # Existing parents untouched, still exactly three users.
    assert len(seed_session.exec(select(UserTable)).all()) == 3
