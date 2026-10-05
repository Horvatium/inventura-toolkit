from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from inventura.core.counting import DocumentStatus
from inventura.core.variance import (
    VarianceRules,
    compute_variance,
    needs_recount,
    status_after_round,
    summarize,
)

RULES = VarianceRules()
D = Decimal


def test_shortage_and_surplus() -> None:
    shortage = compute_variance(D("100"), D("90"), D("2.50"), RULES)
    assert (shortage.quantity, shortage.value, shortage.percent) == (
        D("-10"),
        D("-25.00"),
        D("-10.0"),
    )
    surplus = compute_variance(D("100"), D("103"), D("2.50"), RULES)
    assert (surplus.quantity, surplus.value, surplus.percent) == (D("3"), D("7.50"), D("3.0"))
    assert not compute_variance(D("5"), D("5"), D("9.99"), RULES).has_difference


def test_value_rounds_half_up_to_the_cent() -> None:
    assert compute_variance(D("0"), D("1.5"), D("0.05"), RULES).value == D("0.08")
    assert compute_variance(D("1.5"), D("0"), D("0.05"), RULES).value == D("-0.08")


def test_percent_is_not_computed_for_zero_book() -> None:
    variance = compute_variance(D("0"), D("3"), D("20.00"), RULES)
    assert variance.percent is None
    assert variance.value == D("60.00")


@pytest.mark.parametrize(
    ("value", "percent", "recount"),
    [
        ("50.00", "5.0", True),  # both thresholds exactly reached
        ("-50.00", "-5.0", True),  # shortages count the same
        ("49.99", "80.0", False),  # big deviation, small value
        ("400.00", "4.9", False),  # big value, small deviation
        ("499.99", "0.1", False),
        ("500.00", "0.1", True),  # value alone is enough
        ("-500.00", "-0.1", True),
        ("0.00", "0.0", False),
    ],
)
def test_recount_rule(value: str, percent: str, recount: bool) -> None:
    assert needs_recount(D(value), D(percent), RULES) is recount


@pytest.mark.parametrize(("value", "recount"), [("49.99", False), ("50.00", True), ("-50", True)])
def test_zero_book_only_value_decides(value: str, recount: bool) -> None:
    assert needs_recount(D(value), None, RULES) is recount


def test_rules_from_config_change_the_decision() -> None:
    strict = VarianceRules(min_value=D("10"), min_percent=D("1"), always_value=D("100"))
    assert needs_recount(D("12"), D("2"), strict)
    assert not needs_recount(D("12"), D("2"), RULES)


@pytest.mark.parametrize(
    "kwargs", [{"min_value": D("-1")}, {"always_value": D("-0.01")}, {"max_rounds": 0}]
)
def test_invalid_rules(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        VarianceRules(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("recount", "this_round", "expected"),
    [
        (0, 1, DocumentStatus.ZAKLJUCEN),
        (3, 1, DocumentStatus.PONOVNO_STETJE),
        (3, 2, DocumentStatus.ZAKLJUCEN),  # last allowed round: accepted as counted
        (0, 2, DocumentStatus.ZAKLJUCEN),
    ],
)
def test_status_after_round(recount: int, this_round: int, expected: DocumentStatus) -> None:
    assert status_after_round(recount, this_round, RULES) is expected


def test_summarize() -> None:
    summary = summarize(
        [
            compute_variance(D("10"), D("8"), D("30.00"), RULES),  # -60, recount
            compute_variance(D("10"), D("11"), D("5.00"), RULES),  # +5
            compute_variance(D("4"), D("4"), D("1.00"), RULES),  # no difference
            None,  # not counted
        ]
    )
    assert (summary.items, summary.counted, summary.uncounted) == (4, 3, 1)
    assert (summary.with_difference, summary.recount) == (2, 1)
    assert (summary.surplus_value, summary.shortage_value) == (D("5.00"), D("-60.00"))
    assert (summary.net_value, summary.absolute_value) == (D("-55.00"), D("65.00"))


money = st.decimals(min_value=-10_000, max_value=10_000, places=2)
percents = st.decimals(min_value=-1000, max_value=1000, places=1)


@given(money, percents)
def test_rule_ignores_the_sign(value: Decimal, percent: Decimal) -> None:
    assert needs_recount(value, percent, RULES) == needs_recount(-value, -percent, RULES)


@given(money, money, percents)
def test_a_bigger_value_never_cancels_a_recount(a: Decimal, b: Decimal, percent: Decimal) -> None:
    small, large = sorted((abs(a), abs(b)))
    if needs_recount(small, percent, RULES):
        assert needs_recount(large, percent, RULES)
