"""Validation of stock export rows (book quantities and prices) before they are stored."""

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from inventura.core.locations import Location, LocationError, parse_location
from inventura.core.numbers import NumberFormat, NumberParseError, fits_numeric, parse_decimal
from inventura.core.units import is_valid_quantity, quantity_rule

# Quantities are stored as Numeric(14,3), money as Numeric(14,2).
QUANTITY_PRECISION, QUANTITY_SCALE = 14, 3
MONEY_PRECISION, MONEY_SCALE = 14, 2

MAX_CODE_LENGTH = 40
MAX_TEXT_LENGTH = 200


class StockField(StrEnum):
    """Internal names of the columns of a stock export."""

    SIFRA = "sifra"
    OPIS = "opis"
    MERSKA_ENOTA = "merska_enota"
    LOKACIJA = "lokacija"
    SARZA = "sarza"
    KOLICINA = "kolicina"
    CENA_NA_ENOTO = "cena_na_enoto"


OPTIONAL_FIELDS = frozenset({StockField.SARZA})
REQUIRED_FIELDS = frozenset(StockField) - OPTIONAL_FIELDS

StockKey = tuple[str, Location, str | None]


@dataclass(frozen=True, slots=True)
class StockRow:
    """One valid row of book stock: a material at a location, optionally in a batch."""

    row_number: int
    sifra: str
    opis: str
    merska_enota: str
    lokacija: Location
    sarza: str | None
    kolicina: Decimal
    cena_na_enoto: Decimal

    @property
    def key(self) -> StockKey:
        """Identity of the row; locations compare by parsed value, so K2-03-11 == K2-3-11."""
        return (self.sifra, self.lokacija, self.sarza)


@dataclass(frozen=True, slots=True)
class RowError:
    """A problem in one row of the source file; row_number is the row as shown in Excel."""

    row_number: int
    field: StockField | None
    value: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationResult:
    rows: tuple[StockRow, ...]
    errors: tuple[RowError, ...]
    skipped_blank_rows: int

    @property
    def is_valid(self) -> bool:
        return not self.errors

    @property
    def error_row_count(self) -> int:
        return len({error.row_number for error in self.errors})


RawRecord = Mapping[StockField, object]


def validate_stock_rows(
    records: Iterable[tuple[int, RawRecord]], number_format: NumberFormat
) -> ValidationResult:
    """Validate raw records keyed by field; each record comes with its source row number.

    A row with any error is left out of the result, and every error in it is reported.
    Fully blank rows are skipped. Rows repeating an earlier (sifra, lokacija, sarza) and
    rows whose unit contradicts an earlier row of the same material are errors.
    """
    rows: list[StockRow] = []
    errors: list[RowError] = []
    skipped = 0
    seen_keys: dict[StockKey, int] = {}
    units: dict[str, tuple[str, int]] = {}

    for row_number, record in records:
        if all(_is_blank(value) for value in record.values()):
            skipped += 1
            continue
        row, row_errors = _parse_row(row_number, record, number_format)
        if row is not None:
            row_errors.extend(_check_consistency(row, seen_keys, units))
        if row is None or row_errors:
            errors.extend(row_errors)
            continue
        seen_keys[row.key] = row_number
        units.setdefault(row.sifra, (row.merska_enota, row_number))
        rows.append(row)

    return ValidationResult(rows=tuple(rows), errors=tuple(errors), skipped_blank_rows=skipped)


def _parse_row(
    row_number: int, record: RawRecord, number_format: NumberFormat
) -> tuple[StockRow | None, list[RowError]]:
    errors: list[RowError] = []

    def error(field: StockField, message: str) -> None:
        errors.append(RowError(row_number, field, _display(record.get(field)), message))

    def text(field: StockField, max_length: int) -> str | None:
        value = _text(record.get(field))
        if value is None:
            if field in REQUIRED_FIELDS:
                error(field, "value is required")
            return None
        if len(value) > max_length:
            error(field, f"longer than {max_length} characters")
            return None
        return value

    def number(field: StockField) -> Decimal | None:
        raw = record.get(field)
        if _is_blank(raw):
            error(field, "value is required")
            return None
        try:
            value = parse_decimal(raw, number_format)
        except NumberParseError as exc:
            error(field, str(exc))
            return None
        if value < 0:
            error(field, "must not be negative")
            return None
        return value

    def location() -> Location | None:
        value = text(StockField.LOKACIJA, MAX_CODE_LENGTH)
        if value is None:
            return None
        try:
            return parse_location(value)
        except LocationError as exc:
            error(StockField.LOKACIJA, str(exc))
            return None

    sifra = text(StockField.SIFRA, MAX_CODE_LENGTH)
    opis = text(StockField.OPIS, MAX_TEXT_LENGTH)
    merska_enota = text(StockField.MERSKA_ENOTA, MAX_CODE_LENGTH)
    lokacija = location()
    sarza = text(StockField.SARZA, MAX_CODE_LENGTH)
    kolicina = number(StockField.KOLICINA)
    cena = number(StockField.CENA_NA_ENOTO)

    if kolicina is not None and merska_enota is not None:
        if not is_valid_quantity(kolicina, merska_enota):
            error(StockField.KOLICINA, quantity_rule(merska_enota))
        elif not fits_numeric(kolicina, QUANTITY_PRECISION, QUANTITY_SCALE):
            error(StockField.KOLICINA, "is too large")
    if cena is not None and not fits_numeric(cena, MONEY_PRECISION, MONEY_SCALE):
        error(StockField.CENA_NA_ENOTO, f"must have at most {MONEY_SCALE} decimals")

    if (
        errors
        or sifra is None
        or opis is None
        or merska_enota is None
        or lokacija is None
        or kolicina is None
        or cena is None
    ):
        return None, errors
    row = StockRow(
        row_number=row_number,
        sifra=sifra,
        opis=opis,
        merska_enota=merska_enota,
        lokacija=lokacija,
        sarza=sarza,
        kolicina=kolicina.quantize(Decimal(1).scaleb(-QUANTITY_SCALE)),
        cena_na_enoto=cena.quantize(Decimal(1).scaleb(-MONEY_SCALE)),
    )
    return row, errors


def _check_consistency(
    row: StockRow,
    seen_keys: Mapping[StockKey, int],
    units: Mapping[str, tuple[str, int]],
) -> list[RowError]:
    errors: list[RowError] = []
    first = seen_keys.get(row.key)
    if first is not None:
        errors.append(
            RowError(
                row.row_number,
                None,
                f"{row.sifra} / {row.lokacija} / {row.sarza or ''}",
                f"duplicate of row {first} (same material, location and batch)",
            )
        )
    unit = units.get(row.sifra)
    if unit is not None and unit[0] != row.merska_enota:
        errors.append(
            RowError(
                row.row_number,
                StockField.MERSKA_ENOTA,
                row.merska_enota,
                f"unit differs from {unit[0]!r} in row {unit[1]} for the same material",
            )
        )
    return errors


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    return isinstance(value, str) and not value.strip()


def _text(value: object) -> str | None:
    if _is_blank(value):
        return None
    if isinstance(value, float) and value.is_integer():
        # A code typed into a numeric XLSX cell, e.g. 1234 read back as 1234.0.
        return str(int(value))
    return str(value).strip()


def _display(value: object) -> str:
    return "" if _is_blank(value) else str(value)
