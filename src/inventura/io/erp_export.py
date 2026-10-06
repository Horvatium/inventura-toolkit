"""Write the ERP batch upload: two CSV files and a summary, packed in one ZIP.

This simulates a batch input format; the toolkit has no connection to an ERP.

erp_dokumenti.csv  creates the physical inventory documents (which material to count)
erp_kolicine.csv   enters the counted quantities into those documents

Semicolon separated, decimal comma, no thousands separator, dates as DD.MM.YYYY.
"Nič" is "X" when the count is zero, so the ERP records a counted zero rather than
an empty entry.
"""

import csv
import io
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from inventura.core.erp_export import ErpDocument
from inventura.io.formats import format_date, format_input_quantity

DOCUMENTS_FILE = "erp_dokumenti.csv"
COUNTS_FILE = "erp_kolicine.csv"
SUMMARY_FILE = "povzetek.txt"

DOCUMENT_HEADERS = ("Referenca", "Postavka", "Datum popisa", "Regal", "Material", "Šarža", "ME")
COUNT_HEADERS = ("Referenca", "Postavka", "Material", "Šarža", "Prešteta količina", "ME", "Nič")


@dataclass(frozen=True, slots=True)
class SkippedDocument:
    number: int
    rack: str
    status: str


def erp_zip_name(snapshot_id: int) -> str:
    return f"erp_izvoz_uvoz_{snapshot_id}.zip"


def erp_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def documents_csv(documents: Sequence[ErpDocument]) -> str:
    return _csv(
        DOCUMENT_HEADERS,
        (
            (
                document.reference,
                item.number,
                erp_date(document.count_date),
                document.rack,
                item.sifra,
                item.sarza or "",
                item.merska_enota,
            )
            for document in documents
            for item in document.items
        ),
    )


def counts_csv(documents: Sequence[ErpDocument]) -> str:
    return _csv(
        COUNT_HEADERS,
        (
            (
                document.reference,
                item.number,
                item.sifra,
                item.sarza or "",
                format_input_quantity(item.counted, item.merska_enota),
                item.merska_enota,
                "X" if item.zero_count else "",
            )
            for document in documents
            for item in document.items
        ),
    )


def summary_text(
    snapshot: str,
    documents: Sequence[ErpDocument],
    skipped: Sequence[SkippedDocument],
    created: datetime,
) -> str:
    items = sum(len(document.items) for document in documents)
    lines = [
        f"Izvoz za ERP (simulacija formata) – {snapshot}",
        f"Pripravljeno: {format_date(created.date())} {created:%H:%M}",
        "",
        f"Dokumenti v izvozu: {len(documents)}, postavk: {items}",
        *(f"  {d.reference:<16} regal {d.rack:<5} postavk: {len(d.items)}" for d in documents),
        "",
        f"Izpuščeni dokumenti (niso zaključeni): {len(skipped)}",
        *(f"  {s.number:>3}. regal {s.rack:<5} {s.status}" for s in skipped),
        "",
        "Datoteke:",
        f"  {DOCUMENTS_FILE}  ustvarjanje popisnih dokumentov (material in šarža po regalu)",
        f"  {COUNTS_FILE}  vnos preštetih količin; Nič = X pomeni prešteto, nič ni",
        "",
        "Količine istega materiala in šarže z več lokacij v regalu so seštete.",
        "Ločilo je podpičje, decimalno ločilo vejica, datumi DD.MM.LLLL.",
    ]
    return "\r\n".join(lines) + "\r\n"


def erp_zip(
    snapshot: str,
    documents: Sequence[ErpDocument],
    skipped: Sequence[SkippedDocument],
    created: datetime,
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(DOCUMENTS_FILE, _bom(documents_csv(documents)))
        archive.writestr(COUNTS_FILE, _bom(counts_csv(documents)))
        archive.writestr(SUMMARY_FILE, _bom(summary_text(snapshot, documents, skipped, created)))
    return buffer.getvalue()


def _csv(headers: Sequence[str], rows: Iterable[Sequence[str | int]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return out.getvalue()


def _bom(text: str) -> bytes:
    """UTF-8 with a byte order mark, so Excel shows č, š and ž correctly."""
    return text.encode("utf-8-sig")
