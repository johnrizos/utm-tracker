from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from fastapi import Depends
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from utm_tracker.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str, **kwargs: Any) -> Engine:
    if url.startswith("sqlite"):
        kwargs.setdefault("connect_args", {"check_same_thread": False})
    engine = create_engine(url, pool_pre_ping=True, **kwargs)

    if url.startswith("sqlite"):
        # SQLite ignores foreign keys unless asked.
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_connection: Any, _record: Any) -> None:
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=make_engine(get_settings().database_url), expire_on_commit=False)


def get_session(factory: sessionmaker[Session] = Depends(get_sessionmaker)) -> Iterator[Session]:
    with factory() as session:
        yield session
