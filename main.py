import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import NamedTuple

from dotenv import load_dotenv

load_dotenv()  # must run before any module reads TWILIO_* / DATABASE_URL env vars

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlmodel import Session, SQLModel, select  # noqa: E402

from api.auth_router import auth_router  # noqa: E402
from api.me_router import me_router  # noqa: E402
from api.passcodes import hash_passcode  # noqa: E402
from concierge.factory import describe_handshake_durability  # noqa: E402
from api.router import DEFAULT_BASELINE, DEFAULT_FAMILY_ID, router, schedule_router  # noqa: E402
from api.twilio_webhook import twilio_router  # noqa: E402
from database.connection import engine  # noqa: E402
from database import schema  # noqa: E402, F401 — register table models
from database.schema import BaselineTable, FamilyLink, UserTable  # noqa: E402

_logger = logging.getLogger(__name__)
_one_day = timedelta(days=1)


def parse_allowed_origins(raw: str | None = None) -> list[str]:
    value = (
        raw
        if raw is not None
        else os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
    )
    return [origin.strip() for origin in value.split(",") if origin.strip()]


def allow_sqlite_schema_reset() -> bool:
    return os.getenv("ALLOW_SQLITE_SCHEMA_RESET", "") == "1"


def _seed_passcode_hash(env_var: str) -> str | None:
    """Hash a demo passcode supplied via env, or None to leave login disabled.
    Passcodes are never committed — set SEED_PARENT_*_PASSCODE to enable login."""
    raw = os.getenv(env_var)
    return hash_passcode(raw) if raw else None


def ensure_user_email_column(engine_to_patch) -> None:
    """Add users.email in place on databases created before the column existed.

    SQLModel.metadata.create_all() creates missing *tables*, never missing
    *columns* — so an existing volume would keep a users table with no email
    and every query would fail with "no such column: users.email", crashing the
    app on boot. Idempotent: a no-op once the column is present.
    """
    with engine_to_patch.connect() as connection:
        columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(users)")
        }
        if not columns or "email" in columns:
            # No users table yet (create_all handles it), or already migrated.
            return
        connection.exec_driver_sql("ALTER TABLE users ADD COLUMN email VARCHAR")
        connection.commit()


def ensure_override_end_date_column(engine_to_patch) -> None:
    """Add overrides.end_date in place on databases created before ranges existed."""
    with engine_to_patch.connect() as connection:
        columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(overrides)")
        }
        if not columns or "end_date" in columns:
            return
        connection.exec_driver_sql("ALTER TABLE overrides ADD COLUMN end_date DATE")
        connection.commit()


def ensure_calendar_feed_token_column(engine_to_patch) -> None:
    """Add users.calendar_feed_token on databases created before ICS feeds."""
    with engine_to_patch.connect() as connection:
        columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(users)")
        }
        if not columns or "calendar_feed_token" in columns:
            return
        connection.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN calendar_feed_token VARCHAR"
        )
        connection.commit()
        # Unique index for token lookup; SQLite allows multiple NULLs.
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_calendar_feed_token "
            "ON users (calendar_feed_token)"
        )
        connection.commit()


def ensure_active_day_rows(engine_to_patch) -> None:
    """Backfill active_custody_days for overrides activated before the table
    existed (create_all adds the empty table; this reconstructs its rows).

    Idempotent: existing claims are kept. If two pre-existing active overrides
    overlap — possible only for data created before the constraint — log a
    WARNING naming them and keep the first claimant. Never crash the boot over
    historical data; the constraint governs everything from now on.
    """
    from database.schema import ActiveCustodyDayTable, OverrideTable

    with Session(engine_to_patch) as session:
        active = session.exec(
            select(OverrideTable).where(OverrideTable.is_active.is_(True))
        ).all()
        overlaps: list[tuple[int, int]] = []
        for row in active:
            assert row.id is not None
            end = row.end_date if row.end_date is not None else row.override_date
            day = row.override_date
            while day <= end:
                existing = session.get(
                    ActiveCustodyDayTable, (row.family_id, day)
                )
                if existing is None:
                    session.add(
                        ActiveCustodyDayTable(
                            family_id=row.family_id, day=day, override_id=row.id
                        )
                    )
                elif existing.override_id != row.id:
                    overlaps.append((existing.override_id, row.id))
                day += _one_day
        session.commit()
    if overlaps:
        _logger.warning(
            "active_custody_days backfill found overlapping active overrides "
            "(kept first claimant): %s",
            sorted(set(overlaps)),
        )


class SeedUser(NamedTuple):
    """One row of the declarative seed roster."""

    user_id: int
    role: str
    phone: str | None
    custody_label: str | None
    passcode_env: str
    email_env: str | None


# Reconciled per-user on boot so adding an entry here, or setting a secret that
# wasn't present at first seed, takes effect on the next restart.
_SEED_USERS: tuple[SeedUser, ...] = (
    SeedUser(101, "Parent", "+15550001", "Parent A", "SEED_PARENT_A_PASSCODE", "SEED_PARENT_A_EMAIL"),
    SeedUser(102, "Parent", "+15550002", "Parent B", "SEED_PARENT_B_PASSCODE", "SEED_PARENT_B_EMAIL"),
    SeedUser(2, "Viewer", None, None, "SEED_VIEWER_PASSCODE", None),
)


def ensure_default_seed_data(session: Session) -> None:
    family = session.get(FamilyLink, DEFAULT_FAMILY_ID)
    if family is None:
        session.add(
            FamilyLink(id=DEFAULT_FAMILY_ID, family_name="Default Family")
        )
        session.commit()

    baseline = session.exec(
        select(BaselineTable).where(BaselineTable.family_id == DEFAULT_FAMILY_ID)
    ).first()
    if baseline is None:
        session.add(
            BaselineTable(
                family_id=DEFAULT_FAMILY_ID,
                epoch_start_date=DEFAULT_BASELINE.epoch_start_date,
                starting_parent=DEFAULT_BASELINE.starting_parent.value,
            )
        )
        session.commit()

    # Reconcile the seed roster per-user instead of all-or-nothing: insert any
    # missing user, and back-fill a NULL passcode_hash or email from its env var
    # when the secret is now set. Never overwrite an already-set value — a
    # *changed* passcode is applied only by an explicit volume reset (see README).
    for seed in _SEED_USERS:
        user_id, role, phone, custody_label, passcode_env, email_env = seed
        user = session.get(UserTable, user_id)
        if user is None:
            session.add(
                UserTable(
                    id=user_id,
                    family_id=DEFAULT_FAMILY_ID,
                    role=role,
                    phone=phone,
                    custody_label=custody_label,
                    passcode_hash=_seed_passcode_hash(passcode_env),
                    email=os.getenv(email_env) if email_env else None,
                )
            )
            continue

        if user.email is None and email_env:
            seeded_email = os.getenv(email_env)
            if seeded_email:
                user.email = seeded_email
                session.add(user)

        if user.passcode_hash is None:
            backfilled = _seed_passcode_hash(passcode_env)
            if backfilled is not None:
                user.passcode_hash = backfilled
                session.add(user)
    session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    describe_handshake_durability()
    SQLModel.metadata.create_all(engine)
    # Must run after create_all (which handles fresh databases) and before any
    # query touches users.email on a volume that predates the column.
    ensure_user_email_column(engine)
    ensure_override_end_date_column(engine)
    ensure_calendar_feed_token_column(engine)
    ensure_active_day_rows(engine)
    with Session(engine) as session:
        try:
            ensure_default_seed_data(session)
        except OperationalError:
            # Local SQLite schema drift (e.g. new columns) — recreate empty DB
            # only when explicitly enabled. Never wipe on Fly / production volumes.
            if not allow_sqlite_schema_reset():
                raise
            print(
                "WARNING: SQLite schema drift detected in custody.db — "
                "recreating the database with the current schema."
            )
            session.rollback()
            SQLModel.metadata.drop_all(engine)
            SQLModel.metadata.create_all(engine)
            ensure_default_seed_data(session)
    yield


app = FastAPI(
    title="Custody Scheduler API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(me_router)
app.include_router(router)
app.include_router(schedule_router)
app.include_router(twilio_router)
