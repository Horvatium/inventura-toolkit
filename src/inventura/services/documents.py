"""Create count documents from a snapshot and read them back with progress."""

from dataclasses import dataclass

from sqlalchemy import ColumnElement, Select, exists, func, select
from sqlalchemy.orm import Session, aliased, joinedload

from inventura.core.counting import DocumentStatus
from inventura.core.documents import RackDocument, split_by_rack
from inventura.core.locations import Location
from inventura.core.stock import StockRow
from inventura.db.models import CountDocument, CountItem, Material, StockItem, StockSnapshot
from inventura.services import ConflictError, NotFoundError, bulk_insert


@dataclass(frozen=True, slots=True)
class DocumentProgress:
    document: CountDocument
    item_count: int  # items in the latest round
    counted: int  # of those, items with a counted quantity (0 included)


def create_documents(session: Session, snapshot_id: int) -> list[CountDocument]:
    """One document per rack; book quantity and unit price are frozen into the items."""
    snapshot = session.get(StockSnapshot, snapshot_id, with_for_update=True)
    if snapshot is None:
        raise NotFoundError(f"uvoz {snapshot_id} ne obstaja")
    if session.scalar(select(exists().where(CountDocument.snapshot_id == snapshot_id))):
        raise ConflictError(f"uvoz {snapshot_id} že ima popisne dokumente")

    stock = session.execute(
        select(StockItem, Material)
        .join(Material, StockItem.material_id == Material.id)
        .where(StockItem.snapshot_id == snapshot_id)
    )
    rows: list[StockRow] = []
    by_key: dict[tuple[str, Location, str | None], StockItem] = {}
    for item, material in stock:
        row = StockRow(
            row_number=item.vrstica,
            sifra=material.sifra,
            opis=material.opis,
            merska_enota=material.merska_enota,
            lokacija=Location.from_parts(item.regal, item.nivo, item.polozaj, item.lokacija),
            sarza=item.sarza,
            kolicina=item.kolicina,
            cena_na_enoto=item.cena_na_enoto,
        )
        rows.append(row)
        by_key[row.key] = item

    documents = []
    for rack_document in split_by_rack(rows):
        document = CountDocument(
            snapshot_id=snapshot_id,
            regal=rack_document.rack,
            zaporedna_st=rack_document.number,
        )
        session.add(document)
        session.flush()
        session.execute(
            bulk_insert(CountItem),
            [
                {
                    "document_id": document.id,
                    "material_id": stock_item.material_id,
                    "lokacija": stock_item.lokacija,
                    "nivo": stock_item.nivo,
                    "polozaj": stock_item.polozaj,
                    "sarza": stock_item.sarza,
                    "knjizena_kolicina": stock_item.kolicina,
                    "cena_na_enoto": stock_item.cena_na_enoto,
                    "krog": 1,
                }
                for stock_item in (by_key[row.key] for row in rack_document.items)
            ],
        )
        documents.append(document)
    session.flush()
    return documents


def list_documents(session: Session, snapshot_id: int | None = None) -> list[DocumentProgress]:
    statement = _progress_query()
    if snapshot_id is not None:
        statement = statement.where(CountDocument.snapshot_id == snapshot_id)
    return [DocumentProgress(*row) for row in session.execute(statement)]


def get_document(session: Session, document_id: int) -> DocumentProgress:
    row = session.execute(_progress_query().where(CountDocument.id == document_id)).first()
    if row is None:
        raise NotFoundError(f"dokument {document_id} ne obstaja")
    return DocumentProgress(*row)


def current_round(session: Session, document_id: int) -> int:
    """The count round in progress: 1, or higher once items were sent to a recount."""
    value = session.scalar(
        select(func.coalesce(func.max(CountItem.krog), 1)).where(
            CountItem.document_id == document_id
        )
    )
    return int(value or 1)


def document_items(
    session: Session, document_id: int, round_only: int | None = None
) -> list[CountItem]:
    """Items of the latest count round in walking order, with their material loaded.

    With round_only, just the items of that round (e.g. the ones sent to a recount).
    """
    statement = (
        select(CountItem)
        .join(Material, CountItem.material_id == Material.id)
        .options(joinedload(CountItem.material))
        .where(CountItem.document_id == document_id, is_latest_round())
        .order_by(
            CountItem.nivo,
            CountItem.polozaj,
            Material.sifra,
            CountItem.sarza.asc().nulls_first(),
        )
    )
    if round_only is not None:
        statement = statement.where(CountItem.krog == round_only)
    return list(session.scalars(statement))


def get_item(session: Session, item_id: int) -> CountItem:
    item = session.scalars(
        select(CountItem).options(joinedload(CountItem.material)).where(CountItem.id == item_id)
    ).one_or_none()
    if item is None:
        raise NotFoundError(f"postavka {item_id} ne obstaja")
    return item


def rack_document(session: Session, document_id: int) -> tuple[RackDocument, int, int]:
    """The document as core sees it (for count sheets), the number of documents in its
    snapshot and the round in progress. Quantities and prices are the frozen ones; during
    a recount only the items sent to the recount are included."""
    progress = get_document(session, document_id)
    document = progress.document
    this_round = current_round(session, document_id)
    recount = document.status is DocumentStatus.PONOVNO_STETJE
    items = tuple(
        StockRow(
            row_number=0,
            sifra=item.material.sifra,
            opis=item.material.opis,
            merska_enota=item.material.merska_enota,
            lokacija=Location.from_parts(document.regal, item.nivo, item.polozaj, item.lokacija),
            sarza=item.sarza,
            kolicina=item.knjizena_kolicina,
            cena_na_enoto=item.cena_na_enoto,
        )
        for item in document_items(session, document_id, this_round if recount else None)
    )
    total = session.scalar(
        select(func.count())
        .select_from(CountDocument)
        .where(CountDocument.snapshot_id == document.snapshot_id)
    )
    return RackDocument(document.zaporedna_st, document.regal, items), total or 0, this_round


def is_latest_round() -> ColumnElement[bool]:
    """True for a count item with no later round at the same position (material, location,
    batch). Correlated with CountItem in the enclosing query; uses the unique index."""
    later = aliased(CountItem)
    return ~exists().where(
        later.document_id == CountItem.document_id,
        later.material_id == CountItem.material_id,
        later.nivo == CountItem.nivo,
        later.polozaj == CountItem.polozaj,
        later.sarza.is_not_distinct_from(CountItem.sarza),
        later.krog > CountItem.krog,
    )


def _progress_query() -> Select[CountDocument, int, int]:
    return (
        select(
            CountDocument,
            func.count(CountItem.id),
            func.count(CountItem.presteta_kolicina),
        )
        .outerjoin(
            CountItem,
            (CountItem.document_id == CountDocument.id) & is_latest_round(),
        )
        .group_by(CountDocument.id)
        .order_by(CountDocument.snapshot_id, CountDocument.zaporedna_st)
    )
