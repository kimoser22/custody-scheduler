import os
from collections.abc import Generator

from sqlmodel import Session, create_engine


def resolve_database_url() -> str:
    return os.getenv("DATABASE_URL", "sqlite:///./custody.db")


def sql_echo_enabled() -> bool:
    # Off by default: echo logs every statement and its bound parameters
    # (phone numbers, override descriptions) — must not stream to shipped logs.
    return os.getenv("SQL_ECHO", "") == "1"


DATABASE_URL = resolve_database_url()

engine = create_engine(
    DATABASE_URL,
    echo=sql_echo_enabled(),
    connect_args={"check_same_thread": False},
)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
