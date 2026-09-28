from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from inventura.core.numbers import NumberFormat, NumberParseError, fits_numeric, parse_decimal

SLOVENIAN = NumberFormat(decimal_separator=",", thousands_separator=".")
ENGLISH = NumberFormat(decimal_separator=".", thousands_separator=",")
PLAIN_DOT = NumberFormat(decimal_separator=".", thousands_separator=None)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0", "0"),
        ("12", "12"),
        ("12,5", "12.5"),
        ("0,125", "0.125"),
        ("1.234", "1234"),
        ("1.234,56", "1234.56"),
        ("12.345.678,9", "12345678.9"),
        ("  7,25 ", "7.25"),
        ("-3", "-3"),
        ("+3,0", "3.0"),
    ],
)
def test_parses_slovenian_text(text: str, expected: str) -> None:
    assert parse_decimal(text, SLOVENIAN) == Decimal(expected)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1,234.56", "1234.56"), ("1234.5", "1234.5"), ("0.001", "0.001")],
)
def test_parses_english_text(text: str, expected: str) -> None:
    assert parse_decimal(text, ENGLISH) == Decimal(expected)


def test_space_thousands_separator_accepts_no_break_spaces() -> None:
    fmt = NumberFormat(decimal_separator=",", thousands_separator=" ")
    assert parse_decimal("1 234 567,5", fmt) == Decimal("1234567.5")
    assert parse_decimal("1\u00a0234,5", fmt) == Decimal("1234.5")
    assert parse_decimal("1\u202f234,5", fmt) == Decimal("1234.5")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "abc",
        "1,2,3",
        "1.5",  # a dot is the thousands separator here, so digits must come in threes
        "12.34",
        "1.2345",
        ",5",
        "5,",
        "1e3",
        "NaN",
        "Infinity",
        "--1",
        "1 000",
    ],
)
def test_rejects_invalid_slovenian_text(text: str) -> None:
    with pytest.raises(NumberParseError):
        parse_decimal(text, SLOVENIAN)


def test_without_thousands_separator_grouping_is_rejected() -> None:
    with pytest.raises(NumberParseError):
        parse_decimal("1,234.5", PLAIN_DOT)
    assert parse_decimal("1234.5", PLAIN_DOT) == Decimal("1234.5")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (5, "5"),
        (0.1, "0.1"),
        (12.345, "12.345"),
        (1234.5, "1234.5"),
        (Decimal("3.140"), "3.140"),
    ],
)
def test_numeric_cells_are_converted_without_float_noise(value: object, expected: str) -> None:
    result = parse_decimal(value, SLOVENIAN)
    assert result == Decimal(expected)
    assert str(result) == expected


@pytest.mark.parametrize("value", [True, None, float("nan"), float("inf"), Decimal("NaN"), [1]])
def test_rejects_non_numbers(value: object) -> None:
    with pytest.raises(NumberParseError):
        parse_decimal(value, SLOVENIAN)


@pytest.mark.parametrize(
    ("decimal_separator", "thousands_separator"),
    [(";", None), (",", ","), (".", "."), (",", "_")],
)
def test_invalid_number_formats(decimal_separator: str, thousands_separator: str | None) -> None:
    with pytest.raises(ValueError):
        NumberFormat(decimal_separator, thousands_separator)


@pytest.mark.parametrize(
    ("value", "fits"),
    [
        ("0", True),
        ("12.345", True),
        ("12.3450", True),
        ("12.3456", False),
        ("99999999999.999", True),
        ("100000000000", False),
        ("-5.5", True),
    ],
)
def test_fits_numeric_14_3(value: str, fits: bool) -> None:
    assert fits_numeric(Decimal(value), 14, 3) is fits


def _format(value: Decimal, fmt: NumberFormat) -> str:
    sign = "-" if value < 0 else ""
    integer, _, fraction = format(abs(value), "f").partition(".")
    if fmt.thousands_separator is not None:
        integer = f"{int(integer):,}".replace(",", fmt.thousands_separator)
    return sign + integer + (fmt.decimal_separator + fraction if fraction else "")


@given(
    value=st.decimals(
        min_value=Decimal("-99999999999.999"),
        max_value=Decimal("99999999999.999"),
        places=3,
        allow_nan=False,
        allow_infinity=False,
    ),
    fmt=st.sampled_from([SLOVENIAN, ENGLISH, PLAIN_DOT, NumberFormat(",", " ")]),
)
def test_formatted_numbers_parse_back_exactly(value: Decimal, fmt: NumberFormat) -> None:
    assert parse_decimal(_format(value, fmt), fmt) == value
