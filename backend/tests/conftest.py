"""Shared pytest fixtures.

Tests run against a real PostgreSQL database (``archtutor_test``), not SQLite.
The models use JSONB and Postgres-native enums; a SQLite shim would compile to
something the application never runs against, and would hide exactly the
dialect problems worth catching early.

If PostgreSQL is not reachable the session is skipped with an explicit reason
rather than passing vacuously. See README "Testing" for setup.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import create_app

@pytest.fixture(autouse=True)
def no_tutor() -> Iterator[None]:
    """Run the suite with the tutor switched off, whatever the local .env says.

    A developer with a working provider key configured would otherwise have the
    suite call a paid API, make its assertions depend on a model's mood, and pay
    for it on every run. Tests that exercise the tutor set the settings they
    need themselves, so nothing is lost -- and the tests stop being a live
    integration test by accident.
    """
    from app.core.config import settings

    saved = (
        settings.tutor_base_url,
        settings.tutor_api_key,
        settings.tutor_model,
        settings.tutor_reasoning_effort,
    )
    settings.tutor_base_url = None
    settings.tutor_api_key = None
    settings.tutor_model = None
    settings.tutor_reasoning_effort = None
    try:
        yield
    finally:
        (
            settings.tutor_base_url,
            settings.tutor_api_key,
            settings.tutor_model,
            settings.tutor_reasoning_effort,
        ) = saved


def _test_database_url() -> str:
    from app.core.config import settings

    return settings.database_url


@pytest.fixture(scope="session")
def engine():
    url = _test_database_url()
    try:
        candidate = create_engine(url, pool_pre_ping=True, future=True)
        with candidate.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - surfaced verbatim in the skip reason
        pytest.skip(
            f"PostgreSQL test database unavailable at {url!r} ({exc}). "
            "See README 'Testing'."
        )
    yield candidate
    candidate.dispose()


@pytest.fixture
def db(engine) -> Iterator[Session]:
    """A session with a clean schema for each test."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db) -> Iterator[TestClient]:
    """Test client wired to the transactional test database."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
