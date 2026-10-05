"""Store a validated stock export as a snapshot."""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from inventura.core.stock import StockRow
from inventura.db.models import CountDocument, Material, StockItem, StockSnapshot
from inventura.services import NotFoundError, bulk_insert

MATERIAL_BATCH = 5000


@dataclass(frozen=True, slots=True)
class SnapshotSummary:
    snapshot: StockSnapshot
    item_count: int
    document_count: int


def save_snapshot(session: Session, source: str, rows: Sequence[StockRow]) -> StockSnapshot:
    """Insert a snapshot with its rows; materials are created or updated to the latest data.

    The caller passes only valid rows (an export with row errors is not stored).
    """
    if not rows:
        raise ValueError("a snapshot needs at least one row")
    snapshot = StockSnapshot(izvorna_datoteka=source, stevilo_vrstic=len(rows))
    session.add(snapshot)
    session.flush()

    material_ids = _upsert_materials(session, rows)
    session.execute(
        bulk_insert(StockItem),
        [
            {
                "snapshot_id": snapshot.id,
                "material_id": material_ids[row.sifra],
                "lokacija": str(row.lokacija),
                "regal": row.lokacija.rack,
                "nivo": row.lokacija.level,
                "polozaj": row.lokacija.position,
                "sarza": row.sarza,
                "kolicina": row.kolicina,
                "cena_na_enoto": row.cena_na_enoto,
                "vrstica": row.row_number,
            }
            for row in rows
        ],
    )
    session.flush()
    return snapshot


def list_snapshots(session: Session) -> list[SnapshotSummary]:
    snapshots = session.scalars(select(StockSnapshot).order_by(StockSnapshot.id.desc()))
    return [_summary(session, snapshot) for snapshot in snapshots]


def get_snapshot(session: Session, snapshot_id: int) -> SnapshotSummary:
    snapshot = session.get(StockSnapshot, snapshot_id)
    if snapshot is None:
        raise NotFoundError(f"snapshot {snapshot_id} not found")
    return _summary(session, snapshot)


def _summary(session: Session, snapshot: StockSnapshot) -> SnapshotSummary:
    items = session.scalar(
        select(func.count()).select_from(StockItem).where(StockItem.snapshot_id == snapshot.id)
    )
    documents = session.scalar(
        select(func.count())
        .select_from(CountDocument)
        .where(CountDocument.snapshot_id == snapshot.id)
    )
    return SnapshotSummary(snapshot, items or 0, documents or 0)


def _upsert_materials(session: Session, rows: Sequence[StockRow]) -> dict[str, int]:
    latest = list({row.sifra: row for row in rows}.values())
    ids: dict[str, int] = {}
    # PostgreSQL allows 65535 bind parameters per statement; 4 per material.
    for start in range(0, len(latest), MATERIAL_BATCH):
        statement = pg_insert(Material).values(
            [
                {
                    "sifra": row.sifra,
                    "opis": row.opis,
                    "merska_enota": row.merska_enota,
                    "cena_na_enoto": row.cena_na_enoto,
                }
                for row in latest[start : start + MATERIAL_BATCH]
            ]
        )
        statement = statement.on_conflict_do_update(
            index_elements=[Material.sifra],
            set_={
                "opis": statement.excluded.opis,
                "merska_enota": statement.excluded.merska_enota,
                "cena_na_enoto": statement.excluded.cena_na_enoto,
            },
        )
        returned = session.execute(statement.returning(Material.sifra, Material.id))
        ids.update(returned.all())
    return ids
