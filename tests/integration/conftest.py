"""Integration tests run against a real PostgreSQL database (never SQLite).

Locally: ``docker compose up -d db``. In CI a PostgreSQL service container is used.
The test database is migrated down and up at the start of the session; every test runs
in a transaction that is rolled back, so tests do not see each other's data.
"""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from inventura.settings import Settings, get_settings
from inventura.web.app import create_app
from inventura.web.dependencies import get_session

REPO_ROOT = Path(__file__).resolve().parents[2]


def alembic_config(connection: object) -> Config:
    config = Config(REPO_ROOT / "alembic.ini")
    config.attributes["connection"] = connection
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def make_alembic_config() -> Callable[[object], Config]:
    return alembic_config


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    settings = get_settings()
    if settings.test_database_url == settings.database_url:
        pytest.exit("INVENTURA_TEST_DATABASE_URL must differ from INVENTURA_DATABASE_URL", 2)
    return Settings(
        database_url=settings.test_database_url,
        test_database_url=settings.test_database_url,
        column_mapping=REPO_ROOT / "config" / "column_mapping.yaml",
        max_upload_bytes=settings.max_upload_bytes,
    )


@pytest.fixture(scope="session")
def engine(test_settings: Settings) -> Iterator[Engine]:
    engine = create_engine(test_settings.database_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("select 1"))
    except OperationalError as exc:
        pytest.exit(
            f"PostgreSQL test database is not reachable ({exc.orig}). "
            "Start it with: docker compose up -d db",
            2,
        )
    with engine.begin() as connection:
        config = alembic_config(connection)
        command.downgrade(config, "base")
        command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    # Commits inside the code under test only release a savepoint.
    session = Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(session: Session, test_settings: Settings) -> Iterator[TestClient]:
    app = create_app(test_settings)
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
