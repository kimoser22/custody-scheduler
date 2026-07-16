from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from api.dependencies import get_current_user, get_session
from database import schema  # noqa: F401 — register ORM tables on metadata
from database.schema import FamilyLink, UserTable
from main import app

TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@asynccontextmanager
async def _noop_lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """Swapped in for main.lifespan during tests. The real lifespan seeds
    (and, on schema drift, recreates) database.connection.engine — the actual
    custody.db file, not this module's in-memory test engine. session_fixture
    already prepares whatever DB state each test needs, so startup seeding
    against the real file must never run here."""
    yield


@pytest.fixture(autouse=True)
def _isolate_twilio_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """main.py's load_dotenv() runs at import time and pulls whatever real
    Twilio credentials exist in the developer's local .env into os.environ
    for the whole process — including pytest. Tests must not depend on (or
    be broken by) those real credentials: strip them for every test so
    signature verification and EnvTwilioSmsGateway behave the same
    regardless of what's configured locally."""
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TWILIO_FROM_NUMBER", raising=False)


@pytest.fixture(name="session_fixture")
def _session_fixture() -> Generator[Session, None, None]:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(FamilyLink(id=1, family_name="Test Family"))
        session.commit()
        yield session
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(name="client_fixture")
def _client_fixture(session_fixture: Session) -> Generator[TestClient, None, None]:
    def override_get_session() -> Generator[Session, None, None]:
        yield session_fixture

    app.dependency_overrides[get_session] = override_get_session
    original_lifespan_context = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.router.lifespan_context = original_lifespan_context
        app.dependency_overrides.clear()


@pytest.fixture
def mock_parent() -> UserTable:
    return UserTable(id=1, family_id=1, role="Parent")


@pytest.fixture
def mock_viewer() -> UserTable:
    return UserTable(id=2, family_id=1, role="Viewer")


@pytest.fixture
def mock_other_parent() -> UserTable:
    return UserTable(id=3, family_id=1, role="Parent")
