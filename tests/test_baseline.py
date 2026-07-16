import asyncio
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

import main as main_module
from api.dependencies import get_current_user
from api.router import DEFAULT_BASELINE, DEFAULT_FAMILY_ID, _load_baseline
from core.models import ParentRole
from database.schema import BaselineTable, FamilyLink, UserTable
from main import app, ensure_default_seed_data
from tests.test_api import _override_current_user


def test_load_baseline_is_scoped_to_family(session_fixture: Session) -> None:
    session_fixture.add(FamilyLink(id=2, family_name="Other Family"))
    session_fixture.add(
        BaselineTable(
            family_id=DEFAULT_FAMILY_ID,
            epoch_start_date=date(2026, 1, 5),
            starting_parent=ParentRole.PARENT_A.value,
        )
    )
    session_fixture.add(
        BaselineTable(
            family_id=2,
            epoch_start_date=date(2026, 1, 5),
            starting_parent=ParentRole.PARENT_B.value,
        )
    )
    session_fixture.commit()

    family_one = _load_baseline(session_fixture, family_id=DEFAULT_FAMILY_ID)
    family_two = _load_baseline(session_fixture, family_id=2)

    assert family_one.starting_parent == ParentRole.PARENT_A
    assert family_two.starting_parent == ParentRole.PARENT_B


def test_schedule_uses_seeded_family_baseline(
    client_fixture: TestClient,
    session_fixture: Session,
    mock_viewer: UserTable,
) -> None:
    session_fixture.add(
        BaselineTable(
            family_id=DEFAULT_FAMILY_ID,
            epoch_start_date=date(2026, 1, 5),
            starting_parent=ParentRole.PARENT_B.value,
        )
    )
    session_fixture.commit()

    app.dependency_overrides[get_current_user] = _override_current_user(mock_viewer)

    response = client_fixture.get(
        "/api/v1/schedule/?start_date=2026-01-05&end_date=2026-01-05"
    )

    assert response.status_code == 200
    day = response.json()[0]
    assert day["baseline_parent"] == ParentRole.PARENT_B.value
    assert day["final_parent"] == ParentRole.PARENT_B.value


def test_ensure_default_seed_data_creates_family_and_baseline(
    session_fixture: Session,
) -> None:
    for row in session_fixture.exec(select(UserTable)).all():
        session_fixture.delete(row)
    for row in session_fixture.exec(select(BaselineTable)).all():
        session_fixture.delete(row)
    for row in session_fixture.exec(select(FamilyLink)).all():
        session_fixture.delete(row)
    session_fixture.commit()

    ensure_default_seed_data(session_fixture)

    family = session_fixture.get(FamilyLink, DEFAULT_FAMILY_ID)
    baseline = session_fixture.exec(
        select(BaselineTable).where(BaselineTable.family_id == DEFAULT_FAMILY_ID)
    ).first()
    users = session_fixture.exec(
        select(UserTable).where(UserTable.family_id == DEFAULT_FAMILY_ID)
    ).all()

    assert family is not None
    assert baseline is not None
    assert baseline.epoch_start_date == DEFAULT_BASELINE.epoch_start_date
    assert baseline.starting_parent == DEFAULT_BASELINE.starting_parent.value
    assert len(users) == 3
    phones = {u.phone for u in users if u.phone}
    assert phones == {"+15550001", "+15550002"}

    ensure_default_seed_data(session_fixture)
    baselines = session_fixture.exec(
        select(BaselineTable).where(BaselineTable.family_id == DEFAULT_FAMILY_ID)
    ).all()
    assert len(baselines) == 1


def _isolated_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def test_lifespan_propagates_unrelated_errors_without_wiping_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A seeding bug unrelated to schema drift (e.g. a ValueError) must crash
    startup loudly, not trigger the destructive drop_all/recreate recovery
    path meant only for SQLite schema drift (OperationalError)."""
    monkeypatch.setattr(main_module, "engine", _isolated_engine())

    def fake_seed(session: Session) -> None:
        raise ValueError("unrelated bug, not schema drift")

    monkeypatch.setattr(main_module, "ensure_default_seed_data", fake_seed)

    async def run() -> None:
        async with main_module.lifespan(main_module.app):
            pass

    with pytest.raises(ValueError):
        asyncio.run(run())


def test_lifespan_recreates_db_on_operational_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Genuine schema drift (OperationalError, e.g. "no such column") should
    still trigger the recover-by-recreating-the-DB path."""
    monkeypatch.setattr(main_module, "engine", _isolated_engine())

    seed_calls: list[int] = []

    def flaky_seed(session: Session) -> None:
        seed_calls.append(1)
        if len(seed_calls) == 1:
            raise OperationalError("stmt", {}, Exception("no such column: users.phone"))

    monkeypatch.setattr(main_module, "ensure_default_seed_data", flaky_seed)

    async def run() -> None:
        async with main_module.lifespan(main_module.app):
            pass

    asyncio.run(run())

    assert len(seed_calls) == 2
