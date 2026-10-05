from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from inventura.core.stock import StockField
from inventura.io.column_mapping import ColumnMapping, ColumnMappingError, load_column_mapping

F = StockField

EXPORT_HEADERS = [
    "Šifra materiala",
    "Opis materiala",
    "ME",
    "Lokacija",
    "Šarža",
    "Zaloga",
    "Cena na enoto",
]


def minimal_columns() -> dict[str, Any]:
    return {
        "sifra": ["Šifra"],
        "opis": ["Opis"],
        "merska_enota": ["ME"],
        "lokacija": ["Lokacija"],
        "kolicina": ["Zaloga"],
        "cena_na_enoto": ["Cena"],
    }


def test_repository_config_loads(mapping: ColumnMapping) -> None:
    assert set(mapping.columns) == set(StockField)
    assert mapping.csv.delimiter == ";"
    assert mapping.numbers.to_format().decimal_separator == ","


def test_resolves_export_headers(mapping: ColumnMapping) -> None:
    columns = mapping.resolve([*EXPORT_HEADERS, "Opomba"])
    assert columns[F.SIFRA] == "Šifra materiala"
    assert columns[F.SARZA] == "Šarža"
    assert len(columns) == 7


def test_matching_ignores_case_and_spacing(mapping: ColumnMapping) -> None:
    columns = mapping.resolve([" ŠIFRA  materiala ", "opis", "me", "LOKACIJA", "zaloga", "CENA"])
    assert columns[F.SIFRA] == " ŠIFRA  materiala "
    assert columns[F.CENA_NA_ENOTO] == "CENA"


def test_optional_batch_column_may_be_missing(mapping: ColumnMapping) -> None:
    columns = mapping.resolve([h for h in EXPORT_HEADERS if h != "Šarža"])
    assert F.SARZA not in columns


def test_missing_required_columns_are_listed(mapping: ColumnMapping) -> None:
    with pytest.raises(ColumnMappingError, match=r"manjkajo stolpci: kolicina .*lokacija"):
        mapping.resolve(["Šifra materiala", "Opis materiala", "ME", "Cena na enoto"])


def test_two_columns_for_one_field_is_an_error(mapping: ColumnMapping) -> None:
    with pytest.raises(ColumnMappingError, match="polju opis ustreza več stolpcev"):
        mapping.resolve([*EXPORT_HEADERS, "Opis"])


def test_required_field_without_headers_is_invalid() -> None:
    columns = minimal_columns()
    del columns["lokacija"]
    with pytest.raises(ValidationError, match="no headers configured for: lokacija"):
        ColumnMapping.model_validate({"columns": columns})


def test_header_shared_by_two_fields_is_invalid() -> None:
    columns = minimal_columns() | {"sarza": ["opis"]}
    with pytest.raises(ValidationError, match="used by opis and sarza"):
        ColumnMapping.model_validate({"columns": columns})


def test_empty_header_list_is_invalid() -> None:
    columns = minimal_columns() | {"sarza": []}
    with pytest.raises(ValidationError, match="empty header list"):
        ColumnMapping.model_validate({"columns": columns})


def test_unknown_field_is_invalid() -> None:
    columns = minimal_columns() | {"barva": ["Barva"]}
    with pytest.raises(ValidationError):
        ColumnMapping.model_validate({"columns": columns})


def test_same_separators_are_invalid() -> None:
    with pytest.raises(ValidationError, match="must differ"):
        ColumnMapping.model_validate(
            {
                "columns": minimal_columns(),
                "numbers": {"decimal_separator": ",", "thousands_separator": ","},
            }
        )


def test_load_from_file(tmp_path: Path) -> None:
    path = tmp_path / "mapping.yaml"
    path.write_text(
        "columns:\n"
        "  sifra: [Code]\n  opis: [Name]\n  merska_enota: [Unit]\n"
        "  lokacija: [Bin]\n  kolicina: [Qty]\n  cena_na_enoto: [Price]\n"
        "numbers:\n  decimal_separator: '.'\n  thousands_separator: null\n"
        "csv:\n  delimiter: ','\n",
        encoding="utf-8",
    )
    loaded = load_column_mapping(path)
    assert loaded.csv.delimiter == ","
    assert loaded.numbers.thousands_separator is None
    assert loaded.resolve(["Code", "Name", "Unit", "Bin", "Qty", "Price"])[F.KOLICINA] == "Qty"
