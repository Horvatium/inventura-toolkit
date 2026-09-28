import pytest
from hypothesis import given
from hypothesis import strategies as st

from inventura.core.locations import Location, LocationError, parse_location, rack_sort_key


@pytest.mark.parametrize(
    ("text", "parts"),
    [
        ("B6-1-1", ("B", 6, 1, 1)),
        ("K2-03-11", ("K", 2, 3, 11)),
        ("B10-5-12", ("B", 10, 5, 12)),
        ("AB3-0-7", ("AB", 3, 0, 7)),
        (" b6-1-1 ", ("B", 6, 1, 1)),
    ],
)
def test_parses_rack_level_position(text: str, parts: tuple[str, int, int, int]) -> None:
    location = parse_location(text)
    assert (location.rack_prefix, location.rack_number, location.level, location.position) == parts


def test_leading_zeros_do_not_matter() -> None:
    # Business rule: K2-03-11 and K2-3-11 are the same location.
    assert parse_location("K2-03-11") == parse_location("K2-3-11")
    assert parse_location("K02-003-0011") == parse_location("K2-3-11")
    assert hash(parse_location("K2-03-11")) == hash(parse_location("K2-3-11"))
    assert len({parse_location("K2-03-11"), parse_location("K2-3-11")}) == 1


def test_source_text_is_kept_for_display() -> None:
    location = parse_location(" K2-03-11 ")
    assert str(location) == "K2-03-11"
    assert location.raw == "K2-03-11"
    assert location.canonical == "K2-3-11"
    assert location.rack == "K2"
    assert str(Location("B", 6, 1, 1)) == "B6-1-1"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "B6",
        "B6-1",
        "B6-1-1-1",
        "6-1-1",
        "B-1-1",
        "B6--1",
        "B6-a-1",
        "B6 1 1",
        "B6-1-1x",
        "B6 - 1 - 1",
        "Č6-1-1",
        "B6-1-\u0661",  # an Arabic-Indic digit is not a digit here
        "B12345-1-1",
    ],
)
def test_rejects_invalid_locations(text: str) -> None:
    with pytest.raises(LocationError, match="RACK-LEVEL-POSITION"):
        parse_location(text)


def test_natural_sort_of_racks() -> None:
    texts = ["B10-1-1", "B2-1-1", "K1-01-01", "B1-1-1", "B9-1-1"]
    assert [str(loc) for loc in sorted(map(parse_location, texts))] == [
        "B1-1-1",
        "B2-1-1",
        "B9-1-1",
        "B10-1-1",
        "K1-01-01",
    ]


def test_sort_within_rack_by_level_then_position() -> None:
    texts = ["B6-2-1", "B6-1-10", "B6-1-2", "B6-10-1", "B6-1-1"]
    assert [str(loc) for loc in sorted(map(parse_location, texts))] == [
        "B6-1-1",
        "B6-1-2",
        "B6-1-10",
        "B6-2-1",
        "B6-10-1",
    ]


def test_rack_sort_key() -> None:
    assert sorted(["B10", "b2", "K1", "B9"], key=rack_sort_key) == ["b2", "B9", "B10", "K1"]
    assert rack_sort_key("K02") == ("K", 2)
    with pytest.raises(LocationError):
        rack_sort_key("B-1")


parts = st.tuples(
    st.text(alphabet="ABCKX", min_size=1, max_size=2),
    st.integers(0, 999),
    st.integers(0, 999),
    st.integers(0, 999),
)


def written(prefix: str, rack: int, level: int, position: int, widths: tuple[int, ...]) -> str:
    return f"{prefix}{rack:0{widths[0]}d}-{level:0{widths[1]}d}-{position:0{widths[2]}d}"


@given(parts, st.tuples(*[st.integers(1, 4)] * 3), st.tuples(*[st.integers(1, 4)] * 3))
def test_any_zero_padding_parses_to_the_same_location(
    components: tuple[str, int, int, int], widths_a: tuple[int, ...], widths_b: tuple[int, ...]
) -> None:
    a = parse_location(written(*components, widths_a))
    b = parse_location(written(*components, widths_b))
    assert (a.rack_prefix, a.rack_number, a.level, a.position) == components
    assert a == b


@given(st.lists(parts, max_size=30))
def test_sorting_matches_sorting_the_parsed_values(
    components: list[tuple[str, int, int, int]],
) -> None:
    locations = [parse_location(written(*c, (2, 2, 2))) for c in components]
    ordered = sorted(locations)
    assert [(x.rack_prefix, x.rack_number, x.level, x.position) for x in ordered] == sorted(
        components
    )
