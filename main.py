from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # must run before any module reads TWILIO_* env vars

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlmodel import Session, SQLModel, select  # noqa: E402

from api.router import DEFAULT_BASELINE, DEFAULT_FAMILY_ID, router, schedule_router  # noqa: E402
from api.twilio_webhook import twilio_router  # noqa: E402
from database.connection import engine  # noqa: E402
from database import schema  # noqa: E402, F401 — register table models
from database.schema import BaselineTable, FamilyLink, UserTable  # noqa: E402


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

    existing_users = session.exec(
        select(UserTable).where(UserTable.family_id == DEFAULT_FAMILY_ID)
    ).all()
    if not existing_users:
        session.add(
            UserTable(
                id=101,
                family_id=DEFAULT_FAMILY_ID,
                role="Parent",
                phone="+15550001",
                custody_label="Parent A",
            )
        )
        session.add(
            UserTable(
                id=102,
                family_id=DEFAULT_FAMILY_ID,
                role="Parent",
                phone="+15550002",
                custody_label="Parent B",
            )
        )
        session.add(
            UserTable(
                id=2,
                family_id=DEFAULT_FAMILY_ID,
                role="Viewer",
                phone=None,
                custody_label=None,
            )
        )
        session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        try:
            ensure_default_seed_data(session)
        except OperationalError:
            # Local SQLite schema drift (e.g. new columns) — recreate empty DB.
            # Narrowly scoped to OperationalError (SQLite's "no such column/table")
            # so unrelated bugs during seeding surface loudly instead of wiping data.
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
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(schedule_router)
app.include_router(twilio_router)
