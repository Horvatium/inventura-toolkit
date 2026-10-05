from decimal import Decimal

import pytest

from inventura.core.counting import (
    CountError,
    DocumentClosedError,
    DocumentStatus,
    ItemLockedError,
    check_item_in_round,
    parse_counted_input,
    parse_found_location,
    status_after_count,
    validate_counted_quantity,
    validate_found_quantity,
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
        ("-1", "kos", "ne sme biti negativna"),
        ("1.5", "kos", "mora biti celo število"),
        ("1.5", "kg", "mora biti celo število"),
        ("1.25", "m", "največ 1 decimalko"),
        ("NaN", "kos", "mora biti število"),
        ("1E+12", "kos", "prevelika"),
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


@pytest.mark.parametrize(
    ("text", "expected"),
    [("", None), ("  ", None), ("12", "12"), ("12,5", "12.5"), (" 0 ", "0"), ("3.0", "3.0")],
)
def test_parse_counted_input(text: str, expected: str | None) -> None:
    result = parse_counted_input(text)
    assert result == (None if expected is None else Decimal(expected))


@pytest.mark.parametrize("text", ["abc", "1.234,5", "1,2,3", "12 kos"])
def test_parse_counted_input_rejects_text(text: str) -> None:
    with pytest.raises(CountError, match="mora biti število"):
        parse_counted_input(text)


def test_found_location_must_be_in_the_rack() -> None:
    assert parse_found_location("K2-3-11", "K2").canonical == "K2-3-11"
    assert parse_found_location("k02-03-11", "K2").rack == "K2"
    with pytest.raises(CountError, match="ni v regalu K2"):
        parse_found_location("K3-1-1", "K2")
    with pytest.raises(CountError, match="REGAL-NIVO-POLOŽAJ"):
        parse_found_location("K2-1", "K2")


@pytest.mark.parametrize("quantity", [None, Decimal(0)])
def test_found_goods_need_a_quantity(quantity: Decimal | None) -> None:
    with pytest.raises(CountError, match="večjo od 0"):
        validate_found_quantity(quantity, "kos")


def test_found_quantity_follows_unit_rule() -> None:
    assert validate_found_quantity(Decimal("2.5"), "m") == Decimal("2.500")
    with pytest.raises(CountError, match="celo število"):
        validate_found_quantity(Decimal("2.5"), "kos")


def test_only_the_recount_round_is_editable_during_a_recount() -> None:
    check_item_in_round(DocumentStatus.PONOVNO_STETJE, 2, 2)
    check_item_in_round(DocumentStatus.V_STETJU, 1, 1)
    with pytest.raises(ItemLockedError, match="samo postavke za ponovno štetje"):
        check_item_in_round(DocumentStatus.PONOVNO_STETJE, 1, 2)


def test_status_labels() -> None:
    assert [s.label for s in DocumentStatus] == ["Odprt", "V štetju", "Ponovno štetje", "Zaključen"]
