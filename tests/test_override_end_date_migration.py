"""In-place migration for overrides.end_date on volumes that predate ranges."""

import inspect

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import main
from database.schema import OverrideTable
from main import (
    ensure_calendar_feed_token_column,
    ensure_override_end_date_column,
    ensure_override_notify_status_columns,
    ensure_user_email_column,
)

# Mirrors the sequence in main.lifespan. A legacy volume has to be readable
# after *every* migration runs, not just the one under test — reading through
# the ORM otherwise fails on whichever column was added most recently, which
# has nothing to do with end_date. test_boot_migration_list_is_complete below
# fails loudly if a new migration is added and not listed here.
BOOT_COLUMN_MIGRATIONS = (
    ensure_user_email_column,
    ensure_override_end_date_column,
    ensure_calendar_feed_token_column,
    ensure_override_notify_status_columns,
)


def _apply_boot_column_migrations(engine) -> None:
    for migration in BOOT_COLUMN_MIGRATIONS:
        migration(engine)


def _engine_with_legacy_overrides_table():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE family_links (
                id INTEGER PRIMARY KEY,
                family_name VARCHAR NOT NULL
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE overrides (
                id INTEGER PRIMARY KEY,
                family_id INTEGER NOT NULL,
                override_date DATE NOT NULL,
                assigned_parent VARCHAR NOT NULL,
                override_type VARCHAR NOT NULL,
                description VARCHAR NOT NULL,
                is_active BOOLEAN NOT NULL,
                status VARCHAR NOT NULL,
                requested_by_user_id INTEGER NOT NULL,
                decided_by_user_id INTEGER,
                decided_at DATETIME,
                expires_at DATETIME NOT NULL
            )
            """
        )
        conn.exec_driver_sql(
            "INSERT INTO family_links (id, family_name) VALUES (1, 'Legacy')"
        )
        conn.exec_driver_sql(
            """
            INSERT INTO overrides (
                id, family_id, override_date, assigned_parent, override_type,
                description, is_active, status, requested_by_user_id, expires_at
            ) VALUES (
                1, 1, '2026-01-15', 'Parent A', 'Holiday',
                'legacy', 0, 'Pending', 101, '2026-01-16 12:00:00'
            )
            """
        )
        conn.commit()
    return engine


def _override_columns(engine) -> set[str]:
    with engine.connect() as conn:
        return {
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(overrides)")
        }


def test_migration_adds_missing_end_date_column() -> None:
    """Attribution: this specific helper is what adds end_date."""
    engine = _engine_with_legacy_overrides_table()
    assert "end_date" not in _override_columns(engine)

    ensure_override_end_date_column(engine)

    assert "end_date" in _override_columns(engine)


def test_legacy_volume_is_orm_readable_after_boot_migrations() -> None:
    """The invariant that actually matters: a volume predating these columns
    must be queryable through the ORM once boot has run. This is the check
    that would have caught the users.email crash, so it reads the row rather
    than only inspecting PRAGMA."""
    engine = _engine_with_legacy_overrides_table()

    _apply_boot_column_migrations(engine)

    with Session(engine) as session:
        row = session.get(OverrideTable, 1)
        assert row is not None
        assert row.end_date is None
        assert row.email_notify_status is None
        assert row.sms_notify_status is None


def test_boot_migration_list_is_complete() -> None:
    """Guard against the staleness that broke this file: a new ensure_*_column
    helper added to lifespan but not to BOOT_COLUMN_MIGRATIONS would otherwise
    resurface as a confusing 'no such column' in an unrelated test."""
    declared = {migration.__name__ for migration in BOOT_COLUMN_MIGRATIONS}
    defined = {
        name
        for name, value in inspect.getmembers(main, inspect.isfunction)
        if name.startswith("ensure_") and "column" in name
    }

    assert defined == declared, (
        "main defines column migrations missing from BOOT_COLUMN_MIGRATIONS: "
        f"{sorted(defined - declared)}"
    )


def test_end_date_migration_is_idempotent() -> None:
    engine = _engine_with_legacy_overrides_table()
    ensure_override_end_date_column(engine)
    ensure_override_end_date_column(engine)
    assert "end_date" in _override_columns(engine)


def test_end_date_migration_no_ops_on_fresh_database() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    ensure_override_end_date_column(engine)
    assert "end_date" in _override_columns(engine)
