"""Variances between book and counted quantities, and the rules for a recount.

A variance is computed from the latest count round and never stored. Its sign follows the
count: positive is a surplus (more on the shelf than in the book), negative a shortage.

Every difference goes to a recount, found goods (book quantity 0) included; the unit
price plays no part in that decision and only gives the variance its value in EUR.
After round max_rounds (config/variance_rules.yaml) the counted quantity is accepted.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from inventura.core.counting import DocumentStatus

CENT = Decimal("0.01")
TENTH = Decimal("0.1")


@dataclass(frozen=True, slots=True)
class VarianceRules:
    max_rounds: int = 2  # after this round the result is accepted without another recount

    def __post_init__(self) -> None:
        if self.max_rounds < 1:
            raise ValueError("max_rounds must be at least 1")


@dataclass(frozen=True, slots=True)
class Variance:
    book: Decimal
    counted: Decimal
    unit_price: Decimal
    quantity: Decimal  # counted - book
    value: Decimal  # quantity * unit price, to the cent; for reporting only
    percent: Decimal | None  # quantity / book * 100, to 0.1; None when the book is 0

    @property
    def has_difference(self) -> bool:
        return self.quantity != 0

    @property
    def recount(self) -> bool:
        """Any difference is counted again."""
        return self.has_difference


def compute_variance(book: Decimal, counted: Decimal, unit_price: Decimal) -> Variance:
    quantity = counted - book
    value = (quantity * unit_price).quantize(CENT, rounding=ROUND_HALF_UP)
    percent = None if book == 0 else (quantity / book * 100).quantize(TENTH, rounding=ROUND_HALF_UP)
    return Variance(book, counted, unit_price, quantity, value, percent)


def status_after_round(
    recount_items: int, current_round: int, rules: VarianceRules
) -> DocumentStatus:
    """Status when a count round is finished: recount if needed and allowed, else closed."""
    if recount_items and current_round < rules.max_rounds:
        return DocumentStatus.PONOVNO_STETJE
    return DocumentStatus.ZAKLJUCEN


@dataclass(frozen=True, slots=True)
class VarianceSummary:
    items: int
    counted: int
    with_difference: int
    recount: int
    surplus_value: Decimal  # sum of positive values
    shortage_value: Decimal  # sum of negative values (a negative number)

    @property
    def net_value(self) -> Decimal:
        return self.surplus_value + self.shortage_value

    @property
    def absolute_value(self) -> Decimal:
        return self.surplus_value - self.shortage_value

    @property
    def uncounted(self) -> int:
        return self.items - self.counted


def summarize(variances: Iterable[Variance | None]) -> VarianceSummary:
    """Totals over items; None stands for an item that is not counted yet."""
    items = counted = with_difference = recount = 0
    surplus = shortage = Decimal("0.00")
    for variance in variances:
        items += 1
        if variance is None:
            continue
        counted += 1
        with_difference += variance.has_difference
        recount += variance.recount
        if variance.value > 0:
            surplus += variance.value
        else:
            shortage += variance.value
    return VarianceSummary(items, counted, with_difference, recount, surplus, shortage)
