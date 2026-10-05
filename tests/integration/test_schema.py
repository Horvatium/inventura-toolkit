from collections.abc import Callable
from decimal import Decimal

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, insert, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from inventura.db.models import (
    Base,
    CountDocument,
    CountItem,
    Material,
    StockItem,
    StockSnapshot,
)

TABLES = {"materials", "stock_snapshots", "stock_items", "count_documents", "count_items"}


def test_migrations_match_the_models(engine: Engine) -> None:
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == []


def test_migrations_go_down_and_up(
    engine: Engine, make_alembic_config: Callable[[object], Config]
) -> None:
    with engine.connect() as connection, connection.begin() as transaction:
        config = make_alembic_config(connection)
        command.downgrade(config, "base")
        assert TABLES.isdisjoint(inspect(connection).get_table_names())
        command.upgrade(config, "head")
        assert set(inspect(connection).get_table_names()) >= TABLES
        transaction.rollback()


@pytest.fixture
def document(session: Session) -> CountDocument:
    material = Material(sifra="0000001", opis="Vijak", merska_enota="kos", cena_na_enoto=1)
    snapshot = StockSnapshot(izvorna_datoteka="test.csv", stevilo_vrstic=1)
    session.add_all([material, snapshot])
    session.flush()
    document = CountDocument(snapshot_id=snapshot.id, regal="B6", zaporedna_st=1)
    session.add(document)
    session.flush()
    return document


def count_item(document: CountDocument, sarza: str | None, krog: int = 1) -> dict[str, object]:
    return {
        "document_id": document.id,
        "material_id": select(Material.id).where(Material.sifra == "0000001").scalar_subquery(),
        "lokacija": "B6-1-1",
        "nivo": 1,
        "polozaj": 1,
        "sarza": sarza,
        "knjizena_kolicina": Decimal("5"),
        "cena_na_enoto": Decimal("1.00"),
        "krog": krog,
    }


def test_empty_batch_counts_as_the_same_position(session: Session, document: CountDocument) -> None:
    # NULLS NOT DISTINCT: two rows without a batch at one location clash.
    session.execute(insert(CountItem).values(count_item(document, None)))
    with pytest.raises(IntegrityError, match="uq_count_items_position_round"):
        session.execute(insert(CountItem).values(count_item(document, None)))


def test_next_round_and_other_batch_are_allowed(session: Session, document: CountDocument) -> None:
    session.execute(insert(CountItem).values(count_item(document, None)))
    session.execute(insert(CountItem).values(count_item(document, None, krog=2)))
    session.execute(insert(CountItem).values(count_item(document, "L1")))
    assert session.scalar(select(CountItem.id).where(CountItem.krog == 2)) is not None


def test_negative_quantity_is_rejected(session: Session, document: CountDocument) -> None:
    values = count_item(document, None) | {"presteta_kolicina": Decimal("-1")}
    with pytest.raises(IntegrityError, match="ck_count_items_presteta_not_negative"):
        session.execute(insert(CountItem).values(values))


def test_decimals_round_trip_exactly(session: Session, document: CountDocument) -> None:
    snapshot_id = document.snapshot_id
    session.execute(
        insert(StockItem).values(
            snapshot_id=snapshot_id,
            material_id=select(Material.id).scalar_subquery(),
            lokacija="B6-1-1",
            regal="B6",
            nivo=1,
            polozaj=1,
            kolicina=Decimal("12345678901.5"),
            cena_na_enoto=Decimal("0.10"),
            vrstica=2,
        )
    )
    item = session.scalars(select(StockItem)).one()
    assert item.kolicina == Decimal("12345678901.500")
    assert item.cena_na_enoto == Decimal("0.10")
    assert isinstance(item.kolicina, Decimal)
