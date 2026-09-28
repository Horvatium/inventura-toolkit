"""Split book stock into count documents: one rack is one document."""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from inventura.core.locations import Location
from inventura.core.stock import MONEY_SCALE, StockRow


@dataclass(frozen=True, slots=True)
class RackDocument:
    """The items of one rack in walking order; number is 1-based in natural rack order."""

    number: int
    rack: str
    items: tuple[StockRow, ...]

    @property
    def locations(self) -> tuple[Location, ...]:
        return tuple(dict.fromkeys(item.lokacija for item in self.items))

    @property
    def book_value(self) -> Decimal:
        total = sum((item.kolicina * item.cena_na_enoto for item in self.items), Decimal(0))
        return total.quantize(Decimal(1).scaleb(-MONEY_SCALE))


def walk_order_key(row: StockRow) -> tuple[Location, str, str]:
    """Order within a rack: level, then position, then material and batch.

    Material and batch make the order total, so the result does not depend on the
    order of rows in the export.
    """
    return (row.lokacija, row.sifra, row.sarza or "")


def split_by_rack(rows: Iterable[StockRow]) -> list[RackDocument]:
    """Group rows by rack, sort racks naturally (B2 before B10) and items in walking order."""
    by_rack: dict[tuple[str, int], list[StockRow]] = {}
    for row in rows:
        by_rack.setdefault(row.lokacija.rack_key, []).append(row)

    documents = []
    for number, rack_key in enumerate(sorted(by_rack), start=1):
        items = sorted(by_rack[rack_key], key=walk_order_key)
        documents.append(RackDocument(number, items[0].lokacija.rack, tuple(items)))
    return documents
