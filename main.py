import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # must run before any module reads TWILIO_* / DATABASE_URL env vars

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlmodel import Session, SQLModel, select  # noqa: E402

from api.auth_router import auth_router  # noqa: E402
from api.passcodes import hash_passcode  # noqa: E402
from concierge.factory import warn_ephemeral_handshake_state  # noqa: E402
from api.router import DEFAULT_BASELINE, DEFAULT_FAMILY_ID, router, schedule_router  # noqa: E402
from api.twilio_webhook import twilio_router  # noqa: E402
from database.connection import engine  # noqa: E402
from database import schema  # noqa: E402, F401 — register table models
from database.schema import BaselineTable, FamilyLink, UserTable  # noqa: E402


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


# Declarative seed roster: (user_id, role, phone, custody_label, passcode_env).
# Reconciled per-user on boot so adding an entry here, or setting a passcode
# secret that wasn't present at first seed, takes effect on the next restart.
_SEED_USERS: tuple[tuple[int, str, str | None, str | None, str], ...] = (
    (101, "Parent", "+15550001", "Parent A", "SEED_PARENT_A_PASSCODE"),
    (102, "Parent", "+15550002", "Parent B", "SEED_PARENT_B_PASSCODE"),
    (2, "Viewer", None, None, "SEED_VIEWER_PASSCODE"),
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
    # missing user, and back-fill a NULL passcode_hash from its env var when the
    # secret is now set. Never overwrite an already-set hash — a *changed*
    # passcode is applied only by an explicit volume reset (see README).
    for user_id, role, phone, custody_label, passcode_env in _SEED_USERS:
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
                )
            )
        elif user.passcode_hash is None:
            backfilled = _seed_passcode_hash(passcode_env)
            if backfilled is not None:
                user.passcode_hash = backfilled
                session.add(user)
    session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    warn_ephemeral_handshake_state()
    SQLModel.metadata.create_all(engine)
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
app.include_router(router)
app.include_router(schedule_router)
app.include_router(twilio_router)
