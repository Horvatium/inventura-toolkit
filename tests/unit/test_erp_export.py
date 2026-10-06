from datetime import date
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from inventura.core.erp_export import CountedLine, build_erp_documents, document_reference

D = Decimal
DAY = date(2026, 10, 5)


def line(
    number: int, rack: str, sifra: str, counted: str, sarza: str | None = None, book: str = "0"
) -> CountedLine:
    unit = "m" if sifra.endswith("m") else "kos"
    return CountedLine(number, rack, DAY, sifra, sarza, unit, D(book), D(counted))


def test_reference() -> None:
    assert document_reference(7, "B6") == "INV0007-B6"
    assert document_reference(12345, "K10") == "INV12345-K10"


def test_one_document_per_rack_with_items_summed_per_material_and_batch() -> None:
    documents = build_erp_documents(
        7,
        [
            line(2, "B10", "0000003", "4", book="4"),
            line(1, "B2", "0000002", "3", "L2", book="3"),
            line(1, "B2", "0000001", "5", book="6"),  # B2-1-1
            line(1, "B2", "0000001", "7", book="7"),  # B2-3-4, same material: summed
            line(1, "B2", "0000002", "1", "L1", book="2"),  # other batch: own item
        ],
    )
    assert [(d.reference, d.document_number, d.rack) for d in documents] == [
        ("INV0007-B2", 1, "B2"),
        ("INV0007-B10", 2, "B10"),
    ]
    b2 = documents[0]
    assert [(i.number, i.sifra, i.sarza, i.book, i.counted) for i in b2.items] == [
        (1, "0000001", None, D("13"), D("12")),
        (2, "0000002", "L1", D("2"), D("1")),
        (3, "0000002", "L2", D("3"), D("3")),
    ]
    assert b2.count_date == DAY


def test_zero_count_flag() -> None:
    (document,) = build_erp_documents(1, [line(1, "B1", "0000001", "0", book="5")])
    assert document.items[0].zero_count
    (document,) = build_erp_documents(1, [line(1, "B1", "0000001", "2")])
    assert not document.items[0].zero_count


def test_found_goods_are_exported() -> None:
    (document,) = build_erp_documents(1, [line(1, "B1", "0000009", "2", book="0")])
    assert (document.items[0].book, document.items[0].counted) == (D(0), D(2))


def test_nothing_to_export() -> None:
    assert build_erp_documents(1, []) == []


racks = st.sampled_from(["B1", "B2", "K1"])
codes = st.sampled_from(["0000001", "0000002", "000003m"])
batches = st.sampled_from([None, "L1", "L2"])
quantities = st.integers(0, 500).map(D)


@given(st.lists(st.tuples(racks, codes, batches, quantities, quantities), max_size=40))
def test_no_quantity_is_lost(rows: list[tuple[str, str, str | None, Decimal, Decimal]]) -> None:
    numbers = {"B1": 1, "B2": 2, "K1": 3}
    lines = [
        line(numbers[rack], rack, sifra, str(counted), sarza, book=str(book))
        for rack, sifra, sarza, book, counted in rows
    ]
    documents = build_erp_documents(1, lines)

    items = [item for document in documents for item in document.items]
    assert sum((i.counted for i in items), D(0)) == sum((x.presteta_kolicina for x in lines), D(0))
    assert sum((i.book for i in items), D(0)) == sum((x.knjizena_kolicina for x in lines), D(0))
    for document in documents:
        keys = [(i.sifra, i.sarza) for i in document.items]
        assert len(keys) == len(set(keys))  # one item per material and batch
        assert [i.number for i in document.items] == list(range(1, len(keys) + 1))
