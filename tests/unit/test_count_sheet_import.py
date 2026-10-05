from decimal import Decimal

from inventura.core.count_sheet_import import (
    CountPosition,
    CountUpdate,
    SheetMatch,
    SheetRow,
    match_count_sheet,
)
from inventura.core.locations import parse_location
from inventura.core.numbers import NumberFormat

FMT = NumberFormat(",", ".")
UNITS = {"0000001": "kos", "0000002": "m", "0000003": "kos", "0000009": "kos"}


def position(
    item_id: int, sifra: str, lokacija: str, sarza: str | None = None, **kw: str
) -> CountPosition:
    counted = kw.get("counted")
    return CountPosition(
        item_id=item_id,
        sifra=sifra,
        lokacija=parse_location(lokacija),
        sarza=sarza,
        merska_enota=UNITS[sifra],
        presteta_kolicina=None if counted is None else Decimal(counted),
    )


POSITIONS = [
    position(1, "0000001", "B6-1-1"),
    position(2, "0000002", "B6-1-2", counted="4.5"),
    position(3, "0000003", "B6-2-1", "L1"),
    position(4, "0000003", "B6-2-1", "L2", counted="3"),
]


def row(
    n: int, lokacija: object, sifra: object, kolicina: object, sarza: object = None
) -> SheetRow:
    return SheetRow(n, lokacija, sifra, sarza, kolicina)


def match(*rows: SheetRow) -> SheetMatch:
    return match_count_sheet(rows, "B6", POSITIONS, UNITS, FMT)


def test_rows_update_their_items() -> None:
    result = match(
        row(6, "B6-1-1", "0000001", 12),
        row(7, "B6-1-2", "0000002", "4,5"),
        row(8, "B6-2-1", "0000003", 0, "L1"),
        row(9, "B6-2-1", "0000003", 5.0, "L2"),
    )
    assert result.is_valid
    assert result.updates == [
        CountUpdate(1, Decimal("12.000"), overwritten=False),
        CountUpdate(2, Decimal("4.500"), overwritten=False),  # same value as before
        CountUpdate(3, Decimal("0.000"), overwritten=False),
        CountUpdate(4, Decimal("5.000"), overwritten=True),
    ]
    assert result.found == []


def test_empty_quantity_changes_nothing_and_blank_rows_are_ignored() -> None:
    result = match(row(6, "B6-1-1", "0000001", None), row(7, None, None, None))
    assert result.is_valid
    assert (result.updates, result.without_quantity) == ([], 1)


def test_leading_zeros_in_location_match_the_item() -> None:
    result = match(row(6, "B06-01-01", "0000001", 2))
    assert [u.item_id for u in result.updates] == [1]


def test_unknown_position_with_known_material_is_found_goods() -> None:
    result = match(row(20, "B6-5-5", "0000009", 3, "L9"))
    assert result.is_valid
    (found,) = result.found
    assert (found.row_number, found.sifra, str(found.lokacija), found.sarza) == (
        20,
        "0000009",
        "B6-5-5",
        "L9",
    )
    assert found.quantity == Decimal("3.000")


def test_errors() -> None:
    result = match(
        row(6, "B6-1-1", "0000001", "1,5"),  # whole numbers only
        row(7, "B7-1-1", "0000001", 1),  # other rack
        row(8, "B6-1", "0000001", 1),  # not a location
        row(9, "B6-5-5", "7777777", 1),  # unknown material
        row(10, "B6-5-5", "0000009", 0),  # found goods with zero
        row(11, None, "0000001", 1),  # no location
        row(12, "B6-1-2", "0000002", "abc"),  # not a number
        row(13, "B6-1-2", "0000002", "-1"),  # negative
    )
    assert not result.is_valid
    assert [(e.row_number, e.field) for e in result.errors] == [
        (6, "presteta_kolicina"),
        (7, "lokacija"),
        (8, "lokacija"),
        (9, "sifra"),
        (10, "presteta_kolicina"),
        (11, "lokacija"),
        (12, "presteta_kolicina"),
        (13, "presteta_kolicina"),
    ]
    assert result.errors[1].message == "location B7-1-1 is not in rack B6"
    assert result.errors[3].message == "material is not in the material master data"


def test_same_item_twice_is_an_error() -> None:
    result = match(row(6, "B6-1-1", "0000001", 1), row(7, "B6-01-1", "0000001", 2))
    assert [(e.row_number, e.message) for e in result.errors] == [(7, "same item as row 6")]
