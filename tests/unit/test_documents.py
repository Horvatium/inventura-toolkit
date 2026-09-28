from collections import Counter
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from inventura.core.documents import split_by_rack, walk_order_key
from inventura.core.locations import Location, parse_location
from inventura.core.stock import StockRow


def row(lokacija: str, sifra: str = "0000001", sarza: str | None = None, **kwargs: str) -> StockRow:
    return StockRow(
        row_number=0,
        sifra=sifra,
        opis="Material",
        merska_enota="kos",
        lokacija=parse_location(lokacija),
        sarza=sarza,
        kolicina=Decimal(kwargs.get("kolicina", "1")),
        cena_na_enoto=Decimal(kwargs.get("cena", "1.00")),
    )


def test_one_document_per_rack_in_natural_order() -> None:
    rows = [row("B10-1-1"), row("K1-01-01"), row("B2-1-1"), row("B2-3-1"), row("B9-1-1")]
    documents = split_by_rack(rows)
    assert [(d.number, d.rack, len(d.items)) for d in documents] == [
        (1, "B2", 2),
        (2, "B9", 1),
        (3, "B10", 1),
        (4, "K1", 1),
    ]


def test_items_are_in_walking_order() -> None:
    rows = [
        row("B6-2-1", "0000003"),
        row("B6-1-10", "0000002"),
        row("B6-1-2", "0000009"),
        row("B6-1-2", "0000001", "L2"),
        row("B6-1-2", "0000001", "L1"),
        row("B6-1-2", "0000001"),
    ]
    items = split_by_rack(rows)[0].items
    assert [(str(i.lokacija), i.sifra, i.sarza) for i in items] == [
        ("B6-1-2", "0000001", None),
        ("B6-1-2", "0000001", "L1"),
        ("B6-1-2", "0000001", "L2"),
        ("B6-1-2", "0000009", None),
        ("B6-1-10", "0000002", None),
        ("B6-2-1", "0000003", None),
    ]


def test_rack_written_with_leading_zeros_is_the_same_document() -> None:
    documents = split_by_rack([row("K2-03-11"), row("K02-3-12", "0000002")])
    assert [(d.rack, len(d.items)) for d in documents] == [("K2", 2)]


def test_locations_and_book_value() -> None:
    document = split_by_rack(
        [
            row("B1-1-1", "1", kolicina="3", cena="0.35"),
            row("B1-1-1", "2", kolicina="2", cena="10.10"),
            row("B1-1-2", "3", kolicina="0", cena="99.00"),
        ]
    )[0]
    assert document.locations == (parse_location("B1-1-1"), parse_location("B1-1-2"))
    assert document.book_value == Decimal("21.25")


def test_empty_input_gives_no_documents() -> None:
    assert split_by_rack([]) == []


locations = st.builds(
    Location,
    rack_prefix=st.sampled_from(["B", "K"]),
    rack_number=st.integers(1, 12),
    level=st.integers(1, 5),
    position=st.integers(1, 20),
)
stock_rows = st.builds(
    StockRow,
    row_number=st.integers(2, 10_000),
    sifra=st.sampled_from([f"{n:07d}" for n in range(1, 30)]),
    opis=st.just("Material"),
    merska_enota=st.just("kos"),
    lokacija=locations,
    sarza=st.sampled_from([None, "L1", "L2"]),
    kolicina=st.integers(0, 10_000).map(Decimal),
    cena_na_enoto=st.integers(0, 100_000).map(lambda cents: Decimal(cents).scaleb(-2)),
)
unique_rows = st.lists(stock_rows, max_size=60, unique_by=lambda r: r.key)


@given(st.lists(stock_rows, max_size=60))
def test_no_item_is_lost_or_duplicated(rows: list[StockRow]) -> None:
    documents = split_by_rack(rows)
    items = [item for document in documents for item in document.items]
    assert Counter(items) == Counter(rows)
    assert sum((i.kolicina for i in items), Decimal(0)) == sum(
        (r.kolicina for r in rows), Decimal(0)
    )


@given(st.lists(stock_rows, max_size=60))
def test_each_document_holds_one_rack_in_order(rows: list[StockRow]) -> None:
    documents = split_by_rack(rows)
    assert [d.number for d in documents] == list(range(1, len(documents) + 1))
    rack_keys = [d.items[0].lokacija.rack_key for d in documents]
    assert rack_keys == sorted(set(rack_keys))
    for document in documents:
        assert {item.lokacija.rack for item in document.items} == {document.rack}
        keys = [walk_order_key(item) for item in document.items]
        assert keys == sorted(keys)


@given(unique_rows.flatmap(lambda rows: st.tuples(st.just(rows), st.permutations(rows))))
def test_result_does_not_depend_on_input_order(pair: tuple[list[StockRow], list[StockRow]]) -> None:
    rows, shuffled = pair
    assert split_by_rack(shuffled) == split_by_rack(rows)
