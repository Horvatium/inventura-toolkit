"""Rules for recording counted quantities on count documents."""

from decimal import Decimal
from enum import StrEnum

from inventura.core.numbers import fits_numeric
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

    Zero is a real count (counted, nothing there). The same decimal rule applies
    as for book quantities: whole numbers, one decimal for m and l.
    """
    if quantity is None:
        return None
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
