"""Units of measure and how precisely each one is counted."""

from decimal import Decimal

from inventura.core.numbers import has_at_most_places

# Everything is counted in whole units except goods measured by length or volume.
_QUANTITY_DECIMALS = {"m": 1, "l": 1}


def quantity_decimals(unit: str) -> int:
    """Decimal places a quantity in this unit may have, e.g. 0 for kos, 1 for m."""
    return _QUANTITY_DECIMALS.get(unit.strip().casefold(), 0)


def is_valid_quantity(quantity: Decimal, unit: str) -> bool:
    return has_at_most_places(quantity, quantity_decimals(unit))


def quantity_rule(unit: str) -> str:
    """Human readable rule for error messages."""
    decimals = quantity_decimals(unit)
    if decimals == 0:
        return f"količina v merski enoti {unit!r} mora biti celo število"
    return f"količina v merski enoti {unit!r} ima lahko največ {decimals} decimalko"
