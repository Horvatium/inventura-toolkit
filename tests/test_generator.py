import re
from decimal import Decimal
from pathlib import Path

import pytest

from inventura.core.numbers import NumberFormat
from inventura.core.stock import StockField, validate_stock_rows
from inventura.core.units import is_valid_quantity
from inventura.generator import (
    EXPORT_HEADERS,
    ExportRow,
    generate_stock,
    write_csv,
    write_xlsx,
)
from inventura.io.column_mapping import ColumnMapping
from inventura.io.importer import import_stock_file

B_BIN = re.compile(r"^B[1-9]-[1-5]-(?:[1-9]|10)$")
K_BIN = re.compile(r"^K[1-3]-0[1-4]-(?:0[1-9]|1\d|20)$")


@pytest.fixture(scope="module")
def rows() -> list[ExportRow]:
    return generate_stock(materials=500, seed=7)


def test_same_seed_gives_same_data() -> None:
    assert generate_stock(materials=50, seed=1) == generate_stock(materials=50, seed=1)
    assert generate_stock(materials=50, seed=1) != generate_stock(materials=50, seed=2)


def test_number_of_materials(rows: list[ExportRow]) -> None:
    assert len({row.sifra for row in rows}) == 500
    assert len(rows) >= 500


def test_locations_use_both_notations(rows: list[ExportRow]) -> None:
    for row in rows:
        assert B_BIN.match(row.lokacija) or K_BIN.match(row.lokacija), row.lokacija
    assert any(B_BIN.match(row.lokacija) for row in rows)
    assert any(K_BIN.match(row.lokacija) for row in rows)


def test_material_codes_are_text_with_leading_zeros(rows: list[ExportRow]) -> None:
    assert all(re.fullmatch(r"0\d{6}", row.sifra) for row in rows)


def test_material_attributes_are_consistent(rows: list[ExportRow]) -> None:
    by_code: dict[str, set[tuple[str, str, Decimal]]] = {}
    for row in rows:
        by_code.setdefault(row.sifra, set()).add((row.opis, row.merska_enota, row.cena_na_enoto))
    assert all(len(attributes) == 1 for attributes in by_code.values())


def test_quantities_follow_unit_decimals(rows: list[ExportRow]) -> None:
    assert all(is_valid_quantity(row.kolicina, row.merska_enota) for row in rows)
    assert any(row.kolicina != row.kolicina.to_integral_value() for row in rows)


def test_batches_and_zero_stock_occur(rows: list[ExportRow]) -> None:
    assert any(row.sarza for row in rows)
    assert any(row.sarza is None for row in rows)
    assert any(row.kolicina == 0 for row in rows)


def test_generated_rows_pass_validation(rows: list[ExportRow]) -> None:
    records = (
        (
            number,
            {
                StockField.SIFRA: row.sifra,
                StockField.OPIS: row.opis,
                StockField.MERSKA_ENOTA: row.merska_enota,
                StockField.LOKACIJA: row.lokacija,
                StockField.SARZA: row.sarza,
                StockField.KOLICINA: str(row.kolicina),
                StockField.CENA_NA_ENOTO: str(row.cena_na_enoto),
            },
        )
        for number, row in enumerate(rows, start=2)
    )
    result = validate_stock_rows(records, NumberFormat(".", None))
    assert result.errors == ()


def test_rejects_zero_materials() -> None:
    with pytest.raises(ValueError):
        generate_stock(materials=0)


@pytest.mark.parametrize("suffix", [".csv", ".xlsx"])
def test_written_file_imports_back_unchanged(
    rows: list[ExportRow], mapping: ColumnMapping, tmp_path: Path, suffix: str
) -> None:
    path = tmp_path / f"stock{suffix}"
    (write_csv if suffix == ".csv" else write_xlsx)(rows, path)

    report = import_stock_file(path, mapping)

    assert report.result.errors == ()
    assert set(report.columns.values()) == set(EXPORT_HEADERS.values())
    imported = [
        (r.sifra, r.opis, r.merska_enota, str(r.lokacija), r.sarza, r.kolicina, r.cena_na_enoto)
        for r in report.result.rows
    ]
    expected = [
        (r.sifra, r.opis, r.merska_enota, r.lokacija, r.sarza, r.kolicina, r.cena_na_enoto)
        for r in rows
    ]
    assert imported == expected
