from typing import Any

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from inventura.core.locations import parse_location
from inventura.core.stock import StockRow
from inventura.db.models import CountItem, StockItem
from inventura.generator import generate_stock
from inventura.services.documents import create_documents
from inventura.services.snapshots import save_snapshot


def stock_rows(materials: int) -> list[StockRow]:
    return [
        StockRow(
            row_number=number,
            sifra=row.sifra,
            opis=row.opis,
            merska_enota=row.merska_enota,
            lokacija=parse_location(row.lokacija),
            sarza=row.sarza,
            kolicina=row.kolicina,
            cena_na_enoto=row.cena_na_enoto,
        )
        for number, row in enumerate(generate_stock(materials=materials, seed=5), start=2)
    ]


def test_bulk_inserts_stay_batched_with_and_without_batches(session: Session) -> None:
    # Regression: rows with and without a batch (NULL) used to be inserted one by one.
    rows = stock_rows(300)
    assert any(r.sarza for r in rows) and any(r.sarza is None for r in rows)
    statements: list[Any] = []
    event.listen(
        session.connection(),
        "before_cursor_execute",
        lambda *args: statements.append(args[2]),
    )

    snapshot = save_snapshot(session, "stock.csv", rows)
    documents = create_documents(session, snapshot.id)

    assert len(statements) < 60
    stored = session.scalar(select(func.count()).select_from(StockItem))
    counted = session.scalar(select(func.count()).select_from(CountItem))
    assert stored == counted == len(rows)
    assert len(documents) == 12
