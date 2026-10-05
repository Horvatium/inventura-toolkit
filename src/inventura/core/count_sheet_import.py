"""Match the rows of a filled count sheet to the items of a count document.

Rows are matched by material, location and batch (locations by parsed value, so leading
zeros do not matter). A row with a quantity updates its item, or becomes found goods if
the document has no such item. A row without a quantity changes nothing. A sheet with any
error is rejected as a whole, so the caller stores either everything or nothing.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from inventura.core.counting import (
    CountError,
    check_quantity,
    parse_found_location,
    validate_found_quantity,
)
from inventura.core.locations import Location
from inventura.core.numbers import NumberFormat, NumberParseError, parse_decimal
from inventura.core.stock import RowError, cell_text, display_value, is_blank

LOKACIJA, SIFRA, SARZA, KOLICINA = "lokacija", "sifra", "sarza", "presteta_kolicina"

PositionKey = tuple[str, Location, str | None]


@dataclass(frozen=True, slots=True)
class SheetRow:
    """Raw cell values of one row of a filled count sheet."""

    row_number: int
    lokacija: object
    sifra: object
    sarza: object
    kolicina: object


@dataclass(frozen=True, slots=True)
class CountPosition:
    """An item of the document in its latest round."""

    item_id: int
    sifra: str
    lokacija: Location
    sarza: str | None
    merska_enota: str
    presteta_kolicina: Decimal | None

    @property
    def key(self) -> PositionKey:
        return (self.sifra, self.lokacija, self.sarza)


@dataclass(frozen=True, slots=True)
class CountUpdate:
    item_id: int
    quantity: Decimal
    overwritten: bool  # the item already had a different counted quantity


@dataclass(frozen=True, slots=True)
class FoundGoods:
    row_number: int
    sifra: str
    lokacija: Location
    sarza: str | None
    quantity: Decimal


@dataclass(slots=True)
class SheetMatch:
    updates: list[CountUpdate] = field(default_factory=list)
    found: list[FoundGoods] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    without_quantity: int = 0

    @property
    def is_valid(self) -> bool:
        return not self.errors


def match_count_sheet(
    rows: Iterable[SheetRow],
    rack: str,
    positions: Iterable[CountPosition],
    material_units: Mapping[str, str],
    number_format: NumberFormat,
) -> SheetMatch:
    """Match sheet rows to positions; material_units maps known material codes to units."""
    by_key = {position.key: position for position in positions}
    seen: dict[PositionKey, int] = {}
    result = SheetMatch()

    for row in rows:
        if all(is_blank(v) for v in (row.lokacija, row.sifra, row.sarza, row.kolicina)):
            continue
        if is_blank(row.kolicina):
            result.without_quantity += 1
            continue

        def error(column: str | None, value: object, message: str, row: SheetRow = row) -> None:
            result.errors.append(RowError(row.row_number, column, display_value(value), message))

        sifra = cell_text(row.sifra)
        location_text = cell_text(row.lokacija)
        sarza = cell_text(row.sarza)
        if sifra is None:
            error(SIFRA, row.sifra, "value is required")
        if location_text is None:
            error(LOKACIJA, row.lokacija, "value is required")
        try:
            quantity: Decimal | None = parse_decimal(row.kolicina, number_format)
        except NumberParseError as exc:
            error(KOLICINA, row.kolicina, str(exc))
            quantity = None
        if sifra is None or location_text is None or quantity is None:
            continue
        try:
            location = parse_found_location(location_text, rack)
        except CountError as exc:
            error(LOKACIJA, row.lokacija, str(exc))
            continue

        key = (sifra, location, sarza)
        if key in seen:
            error(None, f"{sifra} / {location} / {sarza or ''}", f"same item as row {seen[key]}")
            continue
        seen[key] = row.row_number

        position = by_key.get(key)
        try:
            if position is not None:
                value = check_quantity(quantity, position.merska_enota)
                overwritten = position.presteta_kolicina not in (None, value)
                result.updates.append(CountUpdate(position.item_id, value, overwritten))
            elif sifra not in material_units:
                error(SIFRA, sifra, "material is not in the material master data")
            else:
                value = validate_found_quantity(quantity, material_units[sifra])
                result.found.append(FoundGoods(row.row_number, sifra, location, sarza, value))
        except CountError as exc:
            error(KOLICINA, row.kolicina, str(exc))

    return result
