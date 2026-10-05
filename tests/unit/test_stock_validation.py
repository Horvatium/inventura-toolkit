from decimal import Decimal

import pytest

from inventura.core.locations import parse_location
from inventura.core.numbers import NumberFormat
from inventura.core.stock import (
    RawRecord,
    StockField,
    StockRow,
    ValidationResult,
    validate_stock_rows,
)

F = StockField
FMT = NumberFormat(",", ".")


def record(**overrides: object) -> RawRecord:
    base: dict[StockField, object] = {
        F.SIFRA: "0001234",
        F.OPIS: "Vijak M8x40",
        F.MERSKA_ENOTA: "kos",
        F.LOKACIJA: "B6-1-1",
        F.SARZA: "",
        F.KOLICINA: "120",
        F.CENA_NA_ENOTO: "0,15",
    }
    for name, value in overrides.items():
        base[F(name)] = value
    return base


def validate(*records: RawRecord) -> ValidationResult:
    return validate_stock_rows(enumerate(records, start=2), FMT)


def test_valid_row_is_converted() -> None:
    result = validate(record(sarza=" L01-0001 ", kolicina="1.234", cena_na_enoto="12,3"))
    assert result.is_valid
    assert result.rows == (
        StockRow(
            row_number=2,
            sifra="0001234",
            opis="Vijak M8x40",
            merska_enota="kos",
            lokacija=parse_location("B6-1-1"),
            sarza="L01-0001",
            kolicina=Decimal("1234.000"),
            cena_na_enoto=Decimal("12.30"),
        ),
    )


def test_quantities_and_prices_are_quantised_to_storage_scale() -> None:
    row = validate(record(kolicina="5", cena_na_enoto="2")).rows[0]
    assert str(row.kolicina) == "5.000"
    assert str(row.cena_na_enoto) == "2.00"


def test_empty_batch_becomes_none() -> None:
    assert validate(record(sarza="  ")).rows[0].sarza is None
    assert validate(record(sarza=None)).rows[0].sarza is None


def test_batch_column_may_be_absent() -> None:
    raw = dict(record())
    del raw[F.SARZA]
    assert validate(raw).rows[0].sarza is None


def test_zero_quantity_is_valid() -> None:
    assert validate(record(kolicina="0")).rows[0].kolicina == Decimal(0)


@pytest.mark.parametrize(
    "field", [F.SIFRA, F.OPIS, F.MERSKA_ENOTA, F.LOKACIJA, F.KOLICINA, F.CENA_NA_ENOTO]
)
def test_required_fields(field: StockField) -> None:
    result = validate(record(**{field.value: " "}))
    assert result.rows == ()
    assert [(e.row_number, e.field, e.message) for e in result.errors] == [
        (2, field, "vrednost je obvezna")
    ]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (F.KOLICINA, "-1", "ne sme biti negativno"),
        (F.KOLICINA, "1,5", "količina v merski enoti 'kos' mora biti celo število"),
        (F.KOLICINA, "100.000.000.000", "je preveliko"),
        (F.KOLICINA, "abc", "ni veljavno število"),
        (F.CENA_NA_ENOTO, "0,005", "ima lahko največ 2 decimalni mesti"),
        (
            F.LOKACIJA,
            "B6-1",
            "neveljavna lokacija, pričakovana oblika REGAL-NIVO-POLOŽAJ, npr. B6-1-1 ali K2-03-11",
        ),
        (F.CENA_NA_ENOTO, "-0,50", "ne sme biti negativno"),
        (F.SIFRA, "X" * 41, "daljše od 40 znakov"),
        (F.OPIS, "X" * 201, "daljše od 200 znakov"),
    ],
)
def test_invalid_values(field: StockField, value: str, message: str) -> None:
    result = validate(record(**{field.value: value}))
    assert result.rows == ()
    (error,) = result.errors
    assert (error.field, error.value, error.message) == (field, value, message)


def test_all_errors_of_a_row_are_reported() -> None:
    result = validate(record(opis="", kolicina="x", cena_na_enoto="-1"))
    assert {e.field for e in result.errors} == {F.OPIS, F.KOLICINA, F.CENA_NA_ENOTO}
    assert result.error_row_count == 1


def test_blank_rows_are_skipped_and_keep_numbering() -> None:
    blank = dict.fromkeys(StockField, "")
    result = validate(record(), blank, record(lokacija="B6-1-2", kolicina="x"))
    assert result.skipped_blank_rows == 1
    assert [e.row_number for e in result.errors] == [4]


def test_duplicate_material_location_batch_is_an_error() -> None:
    result = validate(record(), record(kolicina="5"))
    assert len(result.rows) == 1
    (error,) = result.errors
    assert error.row_number == 3
    assert error.message == "podvojena vrstica 2 (isti material, lokacija in šarža)"


def test_duplicate_location_written_with_leading_zeros() -> None:
    result = validate(record(lokacija="K2-03-11"), record(lokacija="K2-3-11"))
    assert [e.row_number for e in result.errors] == [3]
    assert result.errors[0].message.startswith("podvojena vrstica 2")


@pytest.mark.parametrize(
    ("unit", "quantity", "message"),
    [
        ("m", "12,5", None),
        ("l", "0,5", None),
        ("m", "12,55", "količina v merski enoti 'm' ima lahko največ 1 decimalko"),
        ("kg", "2,5", "količina v merski enoti 'kg' mora biti celo število"),
        ("kos", "3,0", None),
    ],
)
def test_quantity_decimals_depend_on_unit(unit: str, quantity: str, message: str | None) -> None:
    result = validate(record(merska_enota=unit, kolicina=quantity))
    assert [e.message for e in result.errors] == ([message] if message else [])


def test_same_material_in_other_batch_or_location_is_valid() -> None:
    result = validate(record(), record(sarza="L1"), record(sarza="L2"), record(lokacija="K1-01-01"))
    assert result.is_valid
    assert len(result.rows) == 4


def test_unit_must_match_earlier_rows_of_the_same_material() -> None:
    result = validate(record(), record(lokacija="B6-1-2", merska_enota="kg"))
    (error,) = result.errors
    assert (error.row_number, error.field) == (3, F.MERSKA_ENOTA)
    assert error.message == "merska enota se razlikuje od 'kos' v vrstici 2 pri istem materialu"


def test_invalid_row_does_not_block_later_duplicates_check() -> None:
    # The first row is invalid, so the second one is the first valid occurrence.
    result = validate(record(kolicina="x"), record())
    assert [r.row_number for r in result.rows] == [3]


def test_numeric_cells_from_xlsx() -> None:
    result = validate(record(sifra=1234.0, merska_enota="m", kolicina=12.5, cena_na_enoto=3))
    row = result.rows[0]
    assert (row.sifra, row.kolicina, row.cena_na_enoto) == (
        "1234",
        Decimal("12.5"),
        Decimal("3"),
    )


def test_nan_cells_count_as_blank() -> None:
    result = validate(record(sarza=float("nan")))
    assert result.rows[0].sarza is None
