"""Integration tests run against a real PostgreSQL database (never SQLite).

Locally: ``docker compose up -d db``. In CI a PostgreSQL service container is used.
The test database is migrated down and up at the start of the session; every test runs
in a transaction that is rolled back, so tests do not see each other's data.
"""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

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
        variance_rules=REPO_ROOT / "config" / "variance_rules.yaml",
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


STOCK_HEADER = "Šifra materiala;Opis materiala;ME;Lokacija;Šarža;Zaloga;Cena na enoto\n"
STOCK_ROWS = (
    "0000001;Vijak M8;kos;B6-1-1;;120;0,15\n"
    "0000002;Kabel NYM-J;m;B6-1-2;;12,5;0,80\n"
    "0000003;Olje HLP 46;l;B6-2-1;L01;20;3,50\n"
    "0000009;Filter zraka;kos;K1-01-01;;2;40,00\n"
)


@pytest.fixture
def document(client: TestClient) -> dict[str, Any]:
    """The B6 document of a small import (materials 1-3 on B6, material 9 on K1)."""
    data = (STOCK_HEADER + STOCK_ROWS).encode()
    snapshot = client.post("/api/snapshots", files={"file": ("stock.csv", data)}).json()
    created = client.post(f"/api/snapshots/{snapshot['id']}/documents").json()
    b6 = next(d for d in created if d["regal"] == "B6")
    detail: dict[str, Any] = client.get(f"/api/documents/{b6['id']}").json()
    return detail
