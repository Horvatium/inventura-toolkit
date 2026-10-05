"""Rules for recording counted quantities on count documents."""

from decimal import Decimal
from enum import StrEnum

from inventura.core.locations import Location, LocationError, parse_location, rack_sort_key
from inventura.core.numbers import NumberFormat, NumberParseError, fits_numeric, parse_decimal
from inventura.core.stock import QUANTITY_PRECISION, QUANTITY_SCALE
from inventura.core.units import is_valid_quantity, quantity_rule


class DocumentStatus(StrEnum):
    """Life cycle of a count document (one rack)."""

    ODPRT = "odprt"  # created, nothing counted yet
    V_STETJU = "v_stetju"  # at least one item counted
    PONOVNO_STETJE = "ponovno_stetje"  # variances above the threshold sent back for recount
    ZAKLJUCEN = "zakljucen"  # closed, no more changes


class CountError(ValueError):
    """A counted quantity or a count action that the rules do not allow."""


class DocumentClosedError(CountError):
    """The document is closed and cannot be changed."""


def validate_counted_quantity(quantity: Decimal | None, unit: str) -> Decimal | None:
    """Check a counted quantity; None means "not counted yet" and is always allowed.

    Zero is a real count (counted, nothing there).
    """
    return None if quantity is None else check_quantity(quantity, unit)


def check_quantity(quantity: Decimal, unit: str) -> Decimal:
    """The same rule as for book quantities: whole numbers, one decimal for m and l."""
    if not quantity.is_finite():
        raise CountError("quantity must be a number")
    if quantity < 0:
        raise CountError("quantity must not be negative")
    if not is_valid_quantity(quantity, unit):
        raise CountError(quantity_rule(unit))
    if not fits_numeric(quantity, QUANTITY_PRECISION, QUANTITY_SCALE):
        raise CountError("quantity is too large")
    return quantity.quantize(Decimal(1).scaleb(-QUANTITY_SCALE))


def status_after_count(status: DocumentStatus) -> DocumentStatus:
    """Status of a document after a quantity on it has been recorded or cleared."""
    if status is DocumentStatus.ZAKLJUCEN:
        raise DocumentClosedError("document is closed")
    if status is DocumentStatus.ODPRT:
        return DocumentStatus.V_STETJU
    return status


_TYPED = NumberFormat(decimal_separator=".", thousands_separator=None)


def parse_counted_input(text: str) -> Decimal | None:
    """A quantity typed on the tablet: empty means "not counted"; comma or dot as decimals."""
    text = text.strip()
    if not text:
        return None
    try:
        return parse_decimal(text.replace(",", "."), _TYPED)
    except NumberParseError as exc:
        raise CountError("quantity must be a number") from exc


def parse_found_location(text: str, rack: str) -> Location:
    """Location of found goods; it must be in the rack of the document being counted."""
    try:
        location = parse_location(text)
    except LocationError as exc:
        raise CountError(str(exc)) from exc
    if location.rack_key != rack_sort_key(rack):
        raise CountError(f"location {location} is not in rack {rack}")
    return location


def validate_found_quantity(quantity: Decimal | None, unit: str) -> Decimal:
    """Found goods (not in the book) are recorded only with a quantity above zero."""
    if quantity is None or quantity == 0:
        raise CountError("found goods need a quantity greater than 0")
    return check_quantity(quantity, unit)
