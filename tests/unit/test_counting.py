from decimal import Decimal

import pytest

from inventura.core.counting import (
    CountError,
    DocumentClosedError,
    DocumentStatus,
    status_after_count,
    validate_counted_quantity,
)


def test_none_means_not_counted() -> None:
    assert validate_counted_quantity(None, "kos") is None


@pytest.mark.parametrize(
    ("quantity", "unit", "expected"),
    [("0", "kos", "0.000"), ("17", "kos", "17.000"), ("2.5", "m", "2.500"), ("3.0", "l", "3.000")],
)
def test_valid_quantities_are_quantised(quantity: str, unit: str, expected: str) -> None:
    assert str(validate_counted_quantity(Decimal(quantity), unit)) == expected


@pytest.mark.parametrize(
    ("quantity", "unit", "message"),
    [
        ("-1", "kos", "must not be negative"),
        ("1.5", "kos", "must be a whole number"),
        ("1.5", "kg", "must be a whole number"),
        ("1.25", "m", "at most 1 decimal"),
        ("NaN", "kos", "must be a number"),
        ("1E+12", "kos", "too large"),
    ],
)
def test_invalid_quantities(quantity: str, unit: str, message: str) -> None:
    with pytest.raises(CountError, match=message):
        validate_counted_quantity(Decimal(quantity), unit)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (DocumentStatus.ODPRT, DocumentStatus.V_STETJU),
        (DocumentStatus.V_STETJU, DocumentStatus.V_STETJU),
        (DocumentStatus.PONOVNO_STETJE, DocumentStatus.PONOVNO_STETJE),
    ],
)
def test_status_after_count(before: DocumentStatus, after: DocumentStatus) -> None:
    assert status_after_count(before) is after


def test_closed_document_rejects_counts() -> None:
    with pytest.raises(DocumentClosedError):
        status_after_count(DocumentStatus.ZAKLJUCEN)
