from datetime import date
from decimal import Decimal

import pytest

from inventura.io.formats import (
    format_date,
    format_decimal,
    format_quantity,
    quantity_number_format,
)


@pytest.mark.parametrize(
    ("value", "unit", "text"),
    [
        ("1234", "kos", "1.234"),
        ("1234.000", "kos", "1.234"),
        ("12.5", "m", "12,5"),
        ("1250.500", "l", "1.250,5"),
        ("0", "m", "0,0"),
    ],
)
def test_format_quantity(value: str, unit: str, text: str) -> None:
    assert format_quantity(Decimal(value), unit) == text


def test_format_decimal_money() -> None:
    assert format_decimal(Decimal("1234567.891"), 2) == "1.234.567,89"


def test_format_date() -> None:
    assert format_date(date(2026, 9, 8)) == "8. 9. 2026"


def test_quantity_number_format() -> None:
    assert quantity_number_format("kos") == "#,##0"
    assert quantity_number_format("m") == "#,##0.0"
