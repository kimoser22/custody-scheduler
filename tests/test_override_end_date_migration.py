"""In-place migration for overrides.end_date on volumes that predate ranges."""

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from database.schema import OverrideTable
from main import ensure_override_end_date_column


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
    engine = _engine_with_legacy_overrides_table()
    assert "end_date" not in _override_columns(engine)

    ensure_override_end_date_column(engine)

    assert "end_date" in _override_columns(engine)
    with Session(engine) as session:
        row = session.get(OverrideTable, 1)
        assert row is not None
        assert row.end_date is None


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
