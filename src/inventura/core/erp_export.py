"""Shape counted documents for a batch upload into an ERP (a simulated format).

An ERP usually keeps physical inventory per material and batch, without bin locations.
So each count document (one rack) becomes one ERP document, and the quantities of the
same material and batch from different locations in the rack are added up. Only closed
documents are exported: their counts are final.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CountedLine:
    """The final (latest round) count of one position on a closed document."""

    document_number: int
    rack: str
    created: date
    sifra: str
    sarza: str | None
    merska_enota: str
    knjizena_kolicina: Decimal
    presteta_kolicina: Decimal


@dataclass(frozen=True, slots=True)
class ErpItem:
    number: int  # 1, 2, ... within the document
    sifra: str
    sarza: str | None
    merska_enota: str
    book: Decimal
    counted: Decimal

    @property
    def zero_count(self) -> bool:
        """Counted and nothing there; an ERP needs this flag to tell 0 from "not entered"."""
        return self.counted == 0


@dataclass(frozen=True, slots=True)
class ErpDocument:
    reference: str
    document_number: int
    rack: str
    count_date: date
    items: tuple[ErpItem, ...]


def document_reference(snapshot_id: int, rack: str) -> str:
    """A reference the ERP document keeps, so it can be traced back, e.g. INV0007-B6."""
    return f"INV{snapshot_id:04d}-{rack}"


def build_erp_documents(snapshot_id: int, lines: Iterable[CountedLine]) -> list[ErpDocument]:
    """One ERP document per rack, items summed per material and batch, sorted by material."""
    racks: dict[int, tuple[str, date]] = {}
    totals: dict[int, dict[tuple[str, str | None], list[Decimal]]] = {}
    units: dict[str, str] = {}
    for line in lines:
        racks.setdefault(line.document_number, (line.rack, line.created))
        units.setdefault(line.sifra, line.merska_enota)
        key = (line.sifra, line.sarza)
        book_and_counted = totals.setdefault(line.document_number, {}).setdefault(
            key, [Decimal(0), Decimal(0)]
        )
        book_and_counted[0] += line.knjizena_kolicina
        book_and_counted[1] += line.presteta_kolicina

    documents = []
    for number in sorted(racks):
        rack, created = racks[number]
        positions = sorted(
            totals[number].items(), key=lambda entry: (entry[0][0], entry[0][1] or "")
        )
        items = tuple(
            ErpItem(index, sifra, sarza, units[sifra], book, counted)
            for index, ((sifra, sarza), (book, counted)) in enumerate(positions, start=1)
        )
        documents.append(
            ErpDocument(document_reference(snapshot_id, rack), number, rack, created, items)
        )
    return documents
