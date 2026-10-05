from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from inventura.core.counting import DocumentStatus
from inventura.core.variance import (
    VarianceRules,
    compute_variance,
    status_after_round,
    summarize,
)

RULES = VarianceRules()
D = Decimal


def test_shortage_and_surplus() -> None:
    shortage = compute_variance(D("100"), D("90"), D("2.50"))
    assert (shortage.quantity, shortage.value) == (D("-10"), D("-25.00"))
    assert shortage.percent == D("-10.0")
    surplus = compute_variance(D("100"), D("103"), D("2.50"))
    assert (surplus.quantity, surplus.value, surplus.percent) == (D("3"), D("7.50"), D("3.0"))


def test_value_rounds_half_up_to_the_cent() -> None:
    assert compute_variance(D("0"), D("1.5"), D("0.05")).value == D("0.08")
    assert compute_variance(D("1.5"), D("0"), D("0.05")).value == D("-0.08")


def test_percent_is_not_computed_for_zero_book() -> None:
    variance = compute_variance(D("0"), D("3"), D("20.00"))
    assert variance.percent is None
    assert variance.value == D("60.00")


@pytest.mark.parametrize(
    ("book", "counted", "price", "recount"),
    [
        ("1000", "999", "0.02", True),  # one washer: any difference is recounted
        ("10", "9", "5000.00", True),  # one expensive part: the same rule, price does not matter
        ("0", "2", "0.00", True),  # found goods, even without a price
        ("5", "5", "5000.00", False),  # no difference, nothing to recount
        ("12.5", "12.5", "0.80", False),
    ],
)
def test_every_difference_is_recounted(book: str, counted: str, price: str, recount: bool) -> None:
    variance = compute_variance(D(book), D(counted), D(price))
    assert variance.recount is recount
    assert variance.has_difference is recount


def test_invalid_rules() -> None:
    with pytest.raises(ValueError):
        VarianceRules(max_rounds=0)


@pytest.mark.parametrize(
    ("recount", "this_round", "max_rounds", "expected"),
    [
        (0, 1, 2, DocumentStatus.ZAKLJUCEN),
        (3, 1, 2, DocumentStatus.PONOVNO_STETJE),
        (3, 2, 2, DocumentStatus.ZAKLJUCEN),  # last allowed round: accepted as counted
        (3, 2, 3, DocumentStatus.PONOVNO_STETJE),
        (3, 1, 1, DocumentStatus.ZAKLJUCEN),  # a single round: no recount at all
    ],
)
def test_status_after_round(
    recount: int, this_round: int, max_rounds: int, expected: DocumentStatus
) -> None:
    rules = VarianceRules(max_rounds=max_rounds)
    assert status_after_round(recount, this_round, rules) is expected


def test_summarize() -> None:
    summary = summarize(
        [
            compute_variance(D("10"), D("8"), D("30.00")),  # -60
            compute_variance(D("10"), D("11"), D("5.00")),  # +5
            compute_variance(D("4"), D("4"), D("1.00")),  # no difference
            None,  # not counted
        ]
    )
    assert (summary.items, summary.counted, summary.uncounted) == (4, 3, 1)
    assert (summary.with_difference, summary.recount) == (2, 2)
    assert (summary.surplus_value, summary.shortage_value) == (D("5.00"), D("-60.00"))
    assert (summary.net_value, summary.absolute_value) == (D("-55.00"), D("65.00"))


quantities = st.decimals(min_value=0, max_value=100_000, places=1)
prices = st.decimals(min_value=0, max_value=100_000, places=2)


@given(quantities, quantities, prices, prices)
def test_price_never_decides_a_recount(
    book: Decimal, counted: Decimal, price_a: Decimal, price_b: Decimal
) -> None:
    a = compute_variance(book, counted, price_a)
    b = compute_variance(book, counted, price_b)
    assert a.recount == b.recount == (book != counted)


@given(quantities, quantities, prices)
def test_value_is_quantity_times_price(book: Decimal, counted: Decimal, price: Decimal) -> None:
    variance = compute_variance(book, counted, price)
    assert abs(variance.value - (counted - book) * price) <= D("0.005")
    assert (variance.value > 0) == (variance.quantity > 0 and price > 0 and variance.value != 0)
