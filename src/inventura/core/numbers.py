"""Parse decimal numbers from export files without ever going through float arithmetic."""

import math
import re
from dataclasses import dataclass
from decimal import Decimal

DECIMAL_SEPARATORS = frozenset({",", "."})
THOUSANDS_SEPARATORS = frozenset({".", ",", " ", "'"})

# Spreadsheets and locales use several space characters as a thousands separator.
_SPACES = str.maketrans({"\u00a0": " ", "\u202f": " "})


class NumberParseError(ValueError):
    """Raised when a value cannot be read as a decimal number."""


@dataclass(frozen=True, slots=True)
class NumberFormat:
    """How numbers are written in text cells, e.g. ``1.234,5`` (Slovenian) or ``1,234.5``."""

    decimal_separator: str = ","
    thousands_separator: str | None = "."

    def __post_init__(self) -> None:
        if self.decimal_separator not in DECIMAL_SEPARATORS:
            raise ValueError(f"unsupported decimal separator {self.decimal_separator!r}")
        if self.thousands_separator is not None:
            if self.thousands_separator not in THOUSANDS_SEPARATORS:
                raise ValueError(f"unsupported thousands separator {self.thousands_separator!r}")
            if self.thousands_separator == self.decimal_separator:
                raise ValueError("decimal and thousands separators must differ")

    def pattern(self) -> re.Pattern[str]:
        decimal = re.escape(self.decimal_separator)
        if self.thousands_separator is None:
            integer = r"[0-9]+"
        else:
            # Grouped digits must come in threes, so "1.5" is rejected rather than read as 15
            # when the thousands separator is a dot.
            thousands = re.escape(self.thousands_separator)
            integer = rf"[0-9]{{1,3}}(?:{thousands}[0-9]{{3}})+|[0-9]+"
        return re.compile(rf"^([+-]?)({integer})(?:{decimal}([0-9]+))?$")


def parse_decimal(value: object, number_format: NumberFormat) -> Decimal:
    """Convert a cell value (text from CSV, text or number from XLSX) to a finite Decimal."""
    if isinstance(value, bool):
        raise NumberParseError("expected a number")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise NumberParseError("expected a finite number")
        # XLSX stores numbers as binary floats; the shortest repr is the value that was typed.
        return Decimal(repr(value))
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise NumberParseError("expected a finite number")
        return value
    if isinstance(value, str):
        return _parse_text(value, number_format)
    raise NumberParseError(f"unsupported value type {type(value).__name__}")


def _parse_text(value: str, number_format: NumberFormat) -> Decimal:
    text = value.translate(_SPACES).strip()
    if not text:
        raise NumberParseError("expected a number")
    match = number_format.pattern().match(text)
    if match is None:
        raise NumberParseError("not a valid number")
    sign, integer, fraction = match.groups()
    if number_format.thousands_separator is not None:
        integer = integer.replace(number_format.thousands_separator, "")
    digits = f"{sign}{integer}.{fraction}" if fraction else f"{sign}{integer}"
    return Decimal(digits)


def has_at_most_places(value: Decimal, places: int) -> bool:
    """True if value has no non-zero digits beyond the given decimal places (1.50 has 1)."""
    return value == value.quantize(Decimal(1).scaleb(-places))


def fits_numeric(value: Decimal, precision: int, scale: int) -> bool:
    """True if value is storable in SQL ``Numeric(precision, scale)`` without rounding."""
    if abs(value) >= Decimal(10) ** (precision - scale):
        return False
    return has_at_most_places(value, scale)
