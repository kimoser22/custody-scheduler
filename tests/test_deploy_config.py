"""Deploy-related config: DATABASE_URL, CORS origins, schema-reset gate."""

import importlib

import pytest

import database.connection as connection_module
import main as main_module


def test_resolve_database_url_defaults_to_local_sqlite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert connection_module.resolve_database_url() == "sqlite:///./custody.db"


def test_resolve_database_url_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:////data/custody.db")
    assert connection_module.resolve_database_url() == "sqlite:////data/custody.db"


def test_sql_echo_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SQL_ECHO", raising=False)
    assert connection_module.sql_echo_enabled() is False


def test_sql_echo_enabled_by_explicit_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQL_ECHO", "1")
    assert connection_module.sql_echo_enabled() is True

    monkeypatch.setenv("SQL_ECHO", "0")
    assert connection_module.sql_echo_enabled() is False


def test_parse_allowed_origins_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    assert main_module.parse_allowed_origins() == ["http://localhost:3000"]


def test_parse_allowed_origins_comma_separated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000, https://app.vercel.app ",
    )
    assert main_module.parse_allowed_origins() == [
        "http://localhost:3000",
        "https://app.vercel.app",
    ]


def test_allow_sqlite_schema_reset_requires_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ALLOW_SQLITE_SCHEMA_RESET", raising=False)
    assert main_module.allow_sqlite_schema_reset() is False
    monkeypatch.setenv("ALLOW_SQLITE_SCHEMA_RESET", "1")
    assert main_module.allow_sqlite_schema_reset() is True


def test_connection_module_uses_resolve_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Engine is built from resolve_database_url() so Fly can point at /data."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:////data/custody.db")
    reloaded = importlib.reload(connection_module)
    assert reloaded.DATABASE_URL == "sqlite:////data/custody.db"
    # Restore default for other tests that import connection later.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    importlib.reload(connection_module)
