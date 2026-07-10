from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, SQLModel, select

from api.router import DEFAULT_FAMILY_ID, router, schedule_router
from database.connection import engine
from database import schema  # noqa: F401 — register table models
from database.schema import FamilyLink


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        family = session.get(FamilyLink, DEFAULT_FAMILY_ID)
        if family is None:
            session.add(
                FamilyLink(id=DEFAULT_FAMILY_ID, family_name="Default Family")
            )
            session.commit()
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
