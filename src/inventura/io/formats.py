"""Number and date presentation for files people read: Excel formats and Slovenian text."""

from datetime import date
from decimal import Decimal

from inventura.core.units import quantity_decimals

MONEY_NUMBER_FORMAT = "#,##0.00"


def quantity_number_format(unit: str) -> str:
    """Excel number format showing exactly the decimals the unit allows."""
    decimals = quantity_decimals(unit)
    return "#,##0" + ("." + "0" * decimals if decimals else "")


def format_quantity(value: Decimal, unit: str) -> str:
    """Slovenian notation with the unit's decimals, e.g. 1.234 kos or 12,5 m."""
    return format_decimal(value, quantity_decimals(unit))


def format_decimal(value: Decimal, places: int) -> str:
    text = f"{value:,.{places}f}"
    return text.translate(str.maketrans(",.", ".,"))


def format_date(value: date) -> str:
    return f"{value.day}. {value.month}. {value.year}"
