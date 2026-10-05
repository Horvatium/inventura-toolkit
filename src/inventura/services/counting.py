"""Record counts: one quantity at a time, found goods, or a whole filled count sheet."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from inventura.core.count_sheet_import import CountPosition, match_count_sheet
from inventura.core.counting import (
    CountError,
    parse_found_location,
    status_after_count,
    validate_counted_quantity,
    validate_found_quantity,
)
from inventura.core.locations import Location
from inventura.core.numbers import NumberFormat
from inventura.core.stock import QUANTITY_SCALE, RowError, cell_text
from inventura.db.models import CountDocument, CountItem, Material
from inventura.io.count_sheet_reader import read_count_sheet
from inventura.services import ConflictError, NotFoundError
from inventura.services.documents import is_latest_round


@dataclass(frozen=True, slots=True)
class SheetImportSummary:
    updated: int  # items that got a quantity from the sheet
    overwritten: int  # of those, items that already had a different quantity
    found: int  # found goods added
    without_quantity: int  # rows left empty, nothing changed


class CountSheetRejected(Exception):
    """The filled count sheet has row errors; nothing was stored."""

    def __init__(self, errors: list[RowError]) -> None:
        super().__init__(f"popisni list ima napake ({len(errors)}), nič ni uvoženo")
        self.errors = errors


def record_count(
    session: Session,
    item_id: int,
    quantity: Decimal | None,
    counter: str | None,
    now: datetime,
) -> CountItem:
    """Set (or with None, clear) the counted quantity of an item in the latest round.

    Raises NotFoundError, ConflictError for an item of an earlier round,
    DocumentClosedError for a closed document and CountError for an invalid quantity.
    """
    item = session.get(CountItem, item_id, with_for_update=True)
    if item is None:
        raise NotFoundError(f"postavka {item_id} ne obstaja")
    document = _lock_document(session, item.document_id)
    if not session.scalar(select(is_latest_round()).where(CountItem.id == item.id)):
        raise ConflictError(f"postavka {item_id} je iz prejšnjega kroga štetja")

    status = status_after_count(document.status)
    value = validate_counted_quantity(quantity, item.material.merska_enota)
    _set_count(item, value, counter, now)
    document.status = status
    session.flush()
    return item


def add_found_item(
    session: Session,
    document_id: int,
    location: str,
    sifra: str,
    sarza: str | None,
    quantity: Decimal | None,
    counter: str | None,
    now: datetime,
) -> CountItem:
    """Add goods found on the shelf that the book does not have at this location.

    The material must be in the master data; the item gets book quantity 0 and the
    current unit price, so the variance has a value.
    """
    document = _lock_document(session, document_id)
    status = status_after_count(document.status)
    parsed = parse_found_location(location, document.regal)
    code = sifra.strip()
    material = session.scalars(select(Material).where(Material.sifra == code)).one_or_none()
    if material is None:
        raise CountError(f"materiala {code!r} ni v šifrantu")
    value = validate_found_quantity(quantity, material.merska_enota)
    batch = cell_text(sarza)
    if _position_exists(session, document_id, material.id, parsed, batch):
        raise ConflictError(
            "ta material, lokacija in šarža so že na dokumentu; količino vpiši v njihovo vrstico"
        )

    item = _found_item(session, document, material, parsed, batch, value, counter, now)
    document.status = status
    session.flush()
    return item


def delete_found_item(session: Session, item_id: int) -> int:
    """Remove found goods added by mistake; returns the document id."""
    item = session.get(CountItem, item_id, with_for_update=True)
    if item is None:
        raise NotFoundError(f"postavka {item_id} ne obstaja")
    document = _lock_document(session, item.document_id)
    status_after_count(document.status)  # raises for a closed document
    if not item.najdeno:
        raise ConflictError("odstraniti je mogoče samo najdeno blago, knjižne postavke ostanejo")
    session.delete(item)
    session.flush()
    return document.id


def import_count_sheet(
    session: Session,
    document_id: int,
    data: bytes,
    counter: str | None,
    now: datetime,
    number_format: NumberFormat,
) -> SheetImportSummary:
    """Apply a filled Excel count sheet to a document: all rows or none.

    Raises CountSheetError for an unreadable file and CountSheetRejected with row errors.
    """
    document = _lock_document(session, document_id)
    status = status_after_count(document.status)
    rows = read_count_sheet(data, document.regal)

    items = {
        item.id: item
        for item in session.scalars(
            select(CountItem)
            .options(joinedload(CountItem.material))
            .where(CountItem.document_id == document_id, is_latest_round())
            .with_for_update(of=CountItem)
        )
    }
    positions = [
        CountPosition(
            item_id=item.id,
            sifra=item.material.sifra,
            lokacija=Location.from_parts(document.regal, item.nivo, item.polozaj, item.lokacija),
            sarza=item.sarza,
            merska_enota=item.material.merska_enota,
            presteta_kolicina=item.presteta_kolicina,
        )
        for item in items.values()
    ]
    codes = {code for row in rows if (code := cell_text(row.sifra)) is not None}
    materials = {
        material.sifra: material
        for material in session.scalars(select(Material).where(Material.sifra.in_(codes)))
    }
    units = {code: material.merska_enota for code, material in materials.items()}

    match = match_count_sheet(rows, document.regal, positions, units, number_format)
    if not match.is_valid:
        raise CountSheetRejected(match.errors)

    for update in match.updates:
        _set_count(items[update.item_id], update.quantity, counter, now)
    for found in match.found:
        material = materials[found.sifra]
        _found_item(
            session, document, material, found.lokacija, found.sarza, found.quantity, counter, now
        )
    if match.updates or match.found:
        document.status = status
    session.flush()
    return SheetImportSummary(
        updated=len(match.updates),
        overwritten=sum(update.overwritten for update in match.updates),
        found=len(match.found),
        without_quantity=match.without_quantity,
    )


def _lock_document(session: Session, document_id: int) -> CountDocument:
    document = session.scalars(
        select(CountDocument).where(CountDocument.id == document_id).with_for_update()
    ).one_or_none()
    if document is None:
        raise NotFoundError(f"dokument {document_id} ne obstaja")
    return document


def _set_count(item: CountItem, value: Decimal | None, counter: str | None, now: datetime) -> None:
    item.presteta_kolicina = value
    item.stevec = cell_text(counter) if value is not None else None
    item.presteto_ob = now if value is not None else None


def _position_exists(
    session: Session, document_id: int, material_id: int, location: Location, sarza: str | None
) -> bool:
    return bool(
        session.scalar(
            select(func.count())
            .select_from(CountItem)
            .where(
                CountItem.document_id == document_id,
                CountItem.material_id == material_id,
                CountItem.nivo == location.level,
                CountItem.polozaj == location.position,
                CountItem.sarza.is_not_distinct_from(sarza),
            )
        )
    )


def _found_item(
    session: Session,
    document: CountDocument,
    material: Material,
    location: Location,
    sarza: str | None,
    quantity: Decimal,
    counter: str | None,
    now: datetime,
) -> CountItem:
    current_round = session.scalar(
        select(func.coalesce(func.max(CountItem.krog), 1)).where(
            CountItem.document_id == document.id
        )
    )
    item = CountItem(
        document_id=document.id,
        material_id=material.id,
        lokacija=str(location),
        nivo=location.level,
        polozaj=location.position,
        sarza=sarza,
        knjizena_kolicina=Decimal(0).quantize(Decimal(1).scaleb(-QUANTITY_SCALE)),
        cena_na_enoto=material.cena_na_enoto,
        krog=current_round,
        najdeno=True,
    )
    _set_count(item, quantity, counter, now)
    item.material = material
    session.add(item)
    return item
