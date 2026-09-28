from decimal import Decimal

import pytest

from inventura.core.units import is_valid_quantity, quantity_decimals, quantity_rule


@pytest.mark.parametrize(
    ("unit", "decimals"),
    [("kos", 0), ("kg", 0), ("par", 0), ("pak", 0), ("m", 1), ("l", 1), (" M ", 1), ("L", 1)],
)
def test_quantity_decimals(unit: str, decimals: int) -> None:
    assert quantity_decimals(unit) == decimals


@pytest.mark.parametrize(
    ("quantity", "unit", "valid"),
    [
        ("12", "kos", True),
        ("12.000", "kos", True),
        ("12.5", "kos", False),
        ("2.5", "kg", False),
        ("12.5", "m", True),
        ("12.50", "l", True),
        ("12.55", "m", False),
        ("0", "l", True),
    ],
)
def test_is_valid_quantity(quantity: str, unit: str, valid: bool) -> None:
    assert is_valid_quantity(Decimal(quantity), unit) is valid


def test_quantity_rule_messages() -> None:
    assert quantity_rule("kos") == "quantity in 'kos' must be a whole number"
    assert quantity_rule("m") == "quantity in 'm' may have at most 1 decimal"
