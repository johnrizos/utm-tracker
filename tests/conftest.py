import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from utm_tracker.config import Settings, get_settings
from utm_tracker.db import Base, get_sessionmaker, make_engine
from utm_tracker.main import create_app
from utm_tracker.security import create_api_key


@pytest.fixture
def factory() -> Iterator[sessionmaker[Session]]:
    # SQLite in memory by default; CI also runs the suite on PostgreSQL by
    # setting TEST_DATABASE_URL, to catch SQL that only one of them accepts.
    # In memory, StaticPool keeps one shared connection so all sessions see the same data.
    url = os.environ.get("TEST_DATABASE_URL")
    engine = make_engine(url) if url else make_engine("sqlite://", poolclass=StaticPool)

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as s:
        yield s


@pytest.fixture
def client(factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_sessionmaker] = lambda: factory
    app.dependency_overrides[get_settings] = lambda: Settings(
        base_url="https://go.example.com", visitor_secret="test-secret"
    )
    # follow_redirects=False so the tests can look at the redirect itself.
    with TestClient(app, follow_redirects=False) as c:
        yield c


@pytest.fixture
def auth(session: Session) -> dict[str, str]:
    _, key = create_api_key(session, "Marketing")
    return {"X-API-Key": key}


@pytest.fixture
def other_auth(session: Session) -> dict[str, str]:
    _, key = create_api_key(session, "Another team")
    return {"X-API-Key": key}
