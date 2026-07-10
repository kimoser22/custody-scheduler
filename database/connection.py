from collections.abc import Generator

from sqlmodel import Session, create_engine

DATABASE_URL = "sqlite:///./custody.db"

engine = create_engine(DATABASE_URL, echo=True)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
