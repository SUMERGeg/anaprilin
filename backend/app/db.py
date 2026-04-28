from __future__ import annotations

from typing import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


connect_args = {"check_same_thread": False} if _is_sqlite(settings.database_url) else {}
engine = create_engine(settings.database_url, connect_args=connect_args, echo=False)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def init_db() -> None:
    # Import models before create_all to ensure metadata is populated.
    import app.models  # noqa: F401

    SQLModel.metadata.create_all(engine)

