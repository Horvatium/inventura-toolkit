"""Read a stock export (CSV or XLSX), map its columns and validate every row."""

import csv
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePath

import pandas as pd
from openpyxl.utils.exceptions import InvalidFileException

from inventura.core.stock import (
    RawRecord,
    RowError,
    StockField,
    ValidationResult,
    validate_stock_rows,
)
from inventura.io.column_mapping import ColumnMapping

# The header is row 1, so the first data row is row 2, as numbered in Excel.
FIRST_DATA_ROW = 2

SUPPORTED_SUFFIXES = (".csv", ".xlsx")


class UnsupportedFileError(ValueError):
    """The file type is not a supported stock export."""


class UnreadableFileError(ValueError):
    """The file has a supported type but cannot be read (corrupt, wrong encoding, ...)."""


@dataclass(frozen=True, slots=True)
class ImportReport:
    source: str  # file name, for the record of the import
    columns: dict[StockField, str]
    data_rows: int
    result: ValidationResult


def import_stock_file(path: Path, mapping: ColumnMapping) -> ImportReport:
    """Read and validate a stock export from disk.

    Raises UnsupportedFileError, UnreadableFileError, or ColumnMappingError if required
    columns are missing; row problems are reported in the result instead.
    """
    return _import(path, path.name, mapping)


def import_stock_bytes(data: bytes, filename: str, mapping: ColumnMapping) -> ImportReport:
    """Read and validate an uploaded stock export; the file name decides CSV or XLSX."""
    return _import(BytesIO(data), PurePath(filename).name, mapping)


def _import(source: Path | BytesIO, name: str, mapping: ColumnMapping) -> ImportReport:
    frame = _read_frame(source, PurePath(name).suffix.lower(), mapping)
    columns = mapping.resolve([str(header) for header in frame.columns])
    result = validate_stock_rows(_records(frame, columns), mapping.numbers.to_format())
    return ImportReport(source=name, columns=columns, data_rows=len(frame), result=result)


def write_error_report(errors: tuple[RowError, ...], path: Path) -> None:
    """Write row errors as a semicolon-separated CSV that opens directly in Excel."""
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerow(["row", "field", "value", "message"])
        for error in errors:
            writer.writerow([error.row_number, error.field or "", error.value, error.message])


def _read_frame(source: Path | BytesIO, suffix: str, mapping: ColumnMapping) -> pd.DataFrame:
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedFileError(
            f"unsupported file type {suffix!r}; expected one of {', '.join(SUPPORTED_SUFFIXES)}"
        )
    try:
        return _read(source, suffix, mapping)
    except (
        UnicodeDecodeError,
        zipfile.BadZipFile,
        InvalidFileException,
        pd.errors.ParserError,
        pd.errors.EmptyDataError,
    ) as exc:
        raise UnreadableFileError(f"cannot read the file: {exc}") from exc
    except (ValueError, IndexError) as exc:
        # pandas reports a missing worksheet this way.
        raise UnreadableFileError(f"cannot read the file: {exc}") from exc


def _read(source: Path | BytesIO, suffix: str, mapping: ColumnMapping) -> pd.DataFrame:
    if suffix == ".csv":
        # Everything as text: codes keep leading zeros and numbers are parsed as Decimal later.
        return pd.read_csv(
            source,
            sep=mapping.csv.delimiter,
            encoding=mapping.csv.encoding,
            dtype=str,
            na_filter=False,
            skip_blank_lines=False,
        )
    # Native cell types: text stays text, numeric cells arrive as int or float.
    return pd.read_excel(
        source,
        sheet_name=mapping.xlsx.sheet,
        engine="openpyxl",
        dtype=object,
        na_filter=False,
    )


def _records(
    frame: pd.DataFrame, columns: dict[StockField, str]
) -> Iterator[tuple[int, RawRecord]]:
    selected = frame[list(columns.values())]
    fields = list(columns.keys())
    for offset, values in enumerate(selected.itertuples(index=False, name=None)):
        record = {field: _plain(value) for field, value in zip(fields, values, strict=True)}
        yield FIRST_DATA_ROW + offset, record


def _plain(value: object) -> object:
    """Unwrap numpy scalars so the core only sees built-in Python types."""
    item = getattr(value, "item", None)
    return item() if callable(item) else value
