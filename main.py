from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlmodel import SQLModel

from api.router import router
from database.connection import engine
from database import schema  # noqa: F401 — register table models


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(
    title="Custody Scheduler API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)
