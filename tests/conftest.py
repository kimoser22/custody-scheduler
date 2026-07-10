from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

from api.dependencies import get_current_user, get_session
from database import schema  # noqa: F401 — register ORM tables on metadata
from database.schema import UserTable
from main import app

TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@pytest.fixture(name="session_fixture")
def _session_fixture() -> Generator[Session, None, None]:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(name="client_fixture")
def _client_fixture(session_fixture: Session) -> Generator[TestClient, None, None]:
    def override_get_session() -> Generator[Session, None, None]:
        yield session_fixture

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def mock_parent() -> UserTable:
    return UserTable(id=1, family_id=1, role="Parent")


@pytest.fixture
def mock_viewer() -> UserTable:
    return UserTable(id=2, family_id=1, role="Viewer")
