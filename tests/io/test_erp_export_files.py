import csv
import io
import zipfile
from datetime import date, datetime
from decimal import Decimal

from inventura.core.erp_export import ErpDocument, ErpItem
from inventura.io.erp_export import (
    COUNTS_FILE,
    DOCUMENTS_FILE,
    SUMMARY_FILE,
    SkippedDocument,
    counts_csv,
    documents_csv,
    erp_zip,
    erp_zip_name,
)

DOCUMENTS = [
    ErpDocument(
        "INV0007-B2",
        1,
        "B2",
        date(2026, 10, 5),
        (
            ErpItem(1, "0000001", None, "kos", Decimal("13"), Decimal("1234")),
            ErpItem(2, "0000002", "L1", "m", Decimal("2"), Decimal("12.5")),
            ErpItem(3, "0000003", None, "kos", Decimal("3"), Decimal("0")),
        ),
    )
]


def rows(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text), delimiter=";"))


def test_documents_csv() -> None:
    assert rows(documents_csv(DOCUMENTS)) == [
        ["Referenca", "Postavka", "Datum popisa", "Regal", "Material", "Šarža", "ME"],
        ["INV0007-B2", "1", "05.10.2026", "B2", "0000001", "", "kos"],
        ["INV0007-B2", "2", "05.10.2026", "B2", "0000002", "L1", "m"],
        ["INV0007-B2", "3", "05.10.2026", "B2", "0000003", "", "kos"],
    ]


def test_counts_csv_uses_decimal_comma_and_zero_flag() -> None:
    text = counts_csv(DOCUMENTS)
    assert "\r\n" in text
    assert rows(text) == [
        ["Referenca", "Postavka", "Material", "Šarža", "Prešteta količina", "ME", "Nič"],
        ["INV0007-B2", "1", "0000001", "", "1234", "kos", ""],  # no thousands separator
        ["INV0007-B2", "2", "0000002", "L1", "12,5", "m", ""],
        ["INV0007-B2", "3", "0000003", "", "0", "kos", "X"],
    ]


def test_zip_contents() -> None:
    data = erp_zip(
        "Uvoz 7 · zaloga.csv",
        DOCUMENTS,
        [SkippedDocument(2, "B10", "V štetju")],
        datetime(2026, 10, 6, 9, 30),
    )
    archive = zipfile.ZipFile(io.BytesIO(data))
    assert archive.namelist() == [DOCUMENTS_FILE, COUNTS_FILE, SUMMARY_FILE]
    raw = archive.read(COUNTS_FILE)
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM, so Excel shows č, š, ž
    summary = archive.read(SUMMARY_FILE).decode("utf-8-sig")
    assert "Izvoz za ERP (simulacija formata) – Uvoz 7 · zaloga.csv" in summary
    assert "Pripravljeno: 6. 10. 2026 09:30" in summary
    assert "Dokumenti v izvozu: 1, postavk: 3" in summary
    assert "INV0007-B2" in summary
    assert "Izpuščeni dokumenti (niso zaključeni): 1" in summary
    assert "regal B10   V štetju" in summary


def test_zip_name() -> None:
    assert erp_zip_name(7) == "erp_izvoz_uvoz_7.zip"
