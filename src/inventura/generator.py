"""Generate a fictional stock export for demos and tests.

All codes, descriptions, locations and batches are invented; the output only imitates the
shape of a warehouse stock export: material code, description, unit, storage bin, batch,
book quantity and unit price.
"""

import csv
import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from faker import Faker
from openpyxl import Workbook
from openpyxl.styles import Font

from inventura.core.stock import StockField
from inventura.core.units import quantity_decimals
from inventura.io.formats import MONEY_NUMBER_FORMAT, quantity_number_format

# Headers of the generated export; config/column_mapping.yaml accepts them.
EXPORT_HEADERS: dict[StockField, str] = {
    StockField.SIFRA: "Šifra materiala",
    StockField.OPIS: "Opis materiala",
    StockField.MERSKA_ENOTA: "ME",
    StockField.LOKACIJA: "Lokacija",
    StockField.SARZA: "Šarža",
    StockField.KOLICINA: "Zaloga",
    StockField.CENA_NA_ENOTO: "Cena na enoto",
}


@dataclass(frozen=True, slots=True)
class ExportRow:
    sifra: str
    opis: str
    merska_enota: str
    lokacija: str
    sarza: str | None
    kolicina: Decimal
    cena_na_enoto: Decimal


@dataclass(frozen=True, slots=True)
class RackLayout:
    """A group of racks sharing the same bin grid and location notation."""

    prefix: str
    numbers: range
    levels: int
    positions: int
    zero_padded: bool

    def bins(self) -> list[str]:
        width = 2 if self.zero_padded else 1
        return [
            f"{self.prefix}{rack}-{level:0{width}d}-{position:0{width}d}"
            for rack in self.numbers
            for level in range(1, self.levels + 1)
            for position in range(1, self.positions + 1)
        ]


# B racks use the short notation (B6-1-1), K racks the zero-padded one (K2-03-11).
DEFAULT_LAYOUT = (
    RackLayout("B", range(1, 10), levels=5, positions=10, zero_padded=False),
    RackLayout("K", range(1, 4), levels=4, positions=20, zero_padded=True),
)


@dataclass(frozen=True, slots=True)
class _Category:
    unit: str
    price_range: tuple[str, str]  # euros, sampled log-uniformly
    quantity_range: tuple[int, int]  # in steps of the unit's smallest countable amount
    batch_share: float
    describe: Callable[[random.Random], str]


_THREADS = ("M4", "M5", "M6", "M8", "M10", "M12", "M16", "M20")
_BOLT_LENGTHS = (10, 12, 16, 20, 25, 30, 35, 40, 50, 60, 80, 100)
_FINISHES = ("pocinkano", "INOX A2", "INOX A4", "črno")
_BEARINGS = (
    "6000",
    "6001",
    "6002",
    "6004",
    "6201",
    "6203",
    "6204",
    "6205",
    "6206",
    "6305",
    "6308",
)
_CABLES = ("NYM-J", "H07RN-F", "LiYCY", "H05VV-F", "NYY-J")
_CABLE_SIZES = ("2x0,75", "3x1,5", "3x2,5", "4x1,5", "5x2,5", "5x4", "7x1,5")


_CATEGORIES: tuple[_Category, ...] = (
    _Category(
        "kos",
        ("0.02", "1.80"),
        (50, 5000),
        0.0,
        lambda rng: (
            f"Vijak šestrobi DIN 933 {rng.choice(_THREADS)}x{rng.choice(_BOLT_LENGTHS)} "
            f"{rng.choice(_FINISHES)}"
        ),
    ),
    _Category(
        "kos",
        ("0.01", "0.90"),
        (100, 8000),
        0.0,
        lambda rng: f"Matica DIN 934 {rng.choice(_THREADS)} {rng.choice(_FINISHES)}",
    ),
    _Category(
        "kos",
        ("0.01", "0.40"),
        (100, 10000),
        0.0,
        lambda rng: f"Podložka DIN 125 {rng.choice(_THREADS)} {rng.choice(_FINISHES)}",
    ),
    _Category(
        "kos",
        ("3.50", "95.00"),
        (1, 60),
        0.0,
        lambda rng: f"Ležaj kroglični {rng.choice(_BEARINGS)}-{rng.choice(('2RS', 'ZZ'))}",
    ),
    _Category(
        "kos",
        ("0.08", "4.50"),
        (5, 400),
        0.3,
        lambda rng: (
            f"O-tesnilo {rng.randint(5, 120)}x{rng.choice(('1,5', '2', '2,5', '3', '4'))} "
            f"{rng.choice(('NBR', 'FKM', 'EPDM'))}"
        ),
    ),
    _Category(
        "m",
        ("0.35", "14.00"),
        (10, 5000),
        0.0,
        lambda rng: f"Kabel {rng.choice(_CABLES)} {rng.choice(_CABLE_SIZES)} mm2",
    ),
    _Category(
        "m",
        ("0.80", "22.00"),
        (10, 1500),
        0.0,
        lambda rng: (
            f"Cev {rng.choice(('PVC', 'PU', 'PE', 'silikonska'))} "
            f"fi {rng.choice((4, 6, 8, 10, 12, 16, 20, 25))} mm"
        ),
    ),
    _Category(
        "kg",
        ("4.00", "38.00"),
        (1, 180),
        1.0,
        lambda rng: f"Mast {rng.choice(('litijeva EP2', 'za ležaje NLGI 2', 'silikonska'))}",
    ),
    _Category(
        "l",
        ("2.50", "19.00"),
        (10, 4000),
        1.0,
        lambda rng: (
            f"Olje {rng.choice(('hidravlično HLP', 'reduktorsko CLP', 'kompresorsko VDL'))} "
            f"{rng.choice((32, 46, 68, 100, 150, 220))}"
        ),
    ),
    _Category(
        "kos",
        ("6.00", "45.00"),
        (1, 80),
        1.0,
        lambda rng: (
            f"Lepilo za navoje {rng.choice(('srednje trdno', 'visoko trdno', 'nizko trdno'))} "
            f"{rng.choice((10, 50, 250))} ml"
        ),
    ),
    _Category(
        "par",
        ("0.60", "18.00"),
        (10, 600),
        0.0,
        lambda rng: (
            f"Rokavice zaščitne {rng.choice(('nitril', 'usnjene', 'protiurezne'))} "
            f"vel. {rng.randint(7, 11)}"
        ),
    ),
    _Category(
        "kos",
        ("0.40", "65.00"),
        (1, 200),
        0.0,
        lambda rng: rng.choice(
            (
                f"Varovalka {rng.choice((2, 4, 6, 10, 16, 25, 32))} A gG",
                f"Kontaktor {rng.choice(('4', '5,5', '7,5', '11'))} kW 230 V",
                f"Relej {rng.choice(('24 V DC', '230 V AC'))} 2 preklopna kontakta",
                f"Senzor induktivni M{rng.choice((8, 12, 18))} PNP",
            )
        ),
    ),
    _Category(
        "kos",
        ("5.00", "140.00"),
        (1, 40),
        0.0,
        lambda rng: (
            f"Filter {rng.choice(('zraka', 'olja', 'hidravlični'))} "
            f"{rng.choice(('F', 'H', 'P'))}{rng.randint(100, 999)}"
        ),
    ),
    _Category(
        "pak",
        ("1.20", "35.00"),
        (1, 120),
        0.0,
        lambda rng: rng.choice(
            (
                "Trak lepilni rjav 48 mm x 66 m (6 kos)",
                "Folija raztezna 23 my (6 rol)",
                "Vezice kabelske 4,8x200 mm (100 kos)",
                "Krpe čistilne bombažne (10 kg)",
            )
        ),
    ),
)


def generate_stock(
    materials: int = 2000,
    seed: int = 42,
    layout: Sequence[RackLayout] = DEFAULT_LAYOUT,
) -> list[ExportRow]:
    """Generate book stock for the given number of materials; same seed, same output."""
    if materials < 1:
        raise ValueError("materials must be at least 1")
    rng = random.Random(seed)
    fake = Faker("sl_SI")
    fake.seed_instance(seed)
    bins = [bin_ for rack_layout in layout for bin_ in rack_layout.bins()]

    rows: list[ExportRow] = []
    code = 10000
    for _ in range(materials):
        code += rng.randint(1, 9)
        category = rng.choice(_CATEGORIES)
        sifra = f"{code:07d}"
        opis = category.describe(rng)
        price = _price(rng, category)
        locations = rng.sample(bins, 2 if rng.random() < 0.15 else 1)
        for lokacija in locations:
            batch_count = rng.randint(1, 3) if rng.random() < category.batch_share else 0
            batches: list[str | None] = [_batch(fake) for _ in range(batch_count)] or [None]
            for sarza in dict.fromkeys(batches):
                rows.append(
                    ExportRow(
                        sifra=sifra,
                        opis=opis,
                        merska_enota=category.unit,
                        lokacija=lokacija,
                        sarza=sarza,
                        kolicina=_quantity(rng, category),
                        cena_na_enoto=price,
                    )
                )
    return rows


def write_csv(rows: Sequence[ExportRow], path: Path) -> None:
    """Write rows the way a Slovenian ERP export looks: semicolons and decimal commas."""
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file, delimiter=";", lineterminator="\n")
        writer.writerow(EXPORT_HEADERS.values())
        for row in rows:
            writer.writerow(
                [
                    row.sifra,
                    row.opis,
                    row.merska_enota,
                    row.lokacija,
                    row.sarza or "",
                    _comma_decimal(row.kolicina),
                    _comma_decimal(row.cena_na_enoto),
                ]
            )


def write_xlsx(rows: Sequence[ExportRow], path: Path) -> None:
    """Write rows to a single-sheet workbook; codes as text, quantities and prices as numbers."""
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Zaloga"
    sheet.append(list(EXPORT_HEADERS.values()))
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append(
            [
                row.sifra,
                row.opis,
                row.merska_enota,
                row.lokacija,
                row.sarza,
                row.kolicina,
                row.cena_na_enoto,
            ]
        )
    for row, cells in zip(rows, sheet.iter_rows(min_row=2, min_col=6, max_col=7), strict=True):
        cells[0].number_format = quantity_number_format(row.merska_enota)
        cells[1].number_format = MONEY_NUMBER_FORMAT
    for column, width in zip("ABCDEFG", (14, 48, 6, 12, 14, 12, 14), strict=True):
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A2"
    workbook.save(path)


def _price(rng: random.Random, category: _Category) -> Decimal:
    # Floats are only used to sample; the price itself is built from whole cents.
    low, high = (math.log(float(Decimal(bound) * 100)) for bound in category.price_range)
    cents = round(math.exp(rng.uniform(low, high)))
    return Decimal(max(cents, 1)).scaleb(-2)


def _quantity(rng: random.Random, category: _Category) -> Decimal:
    # A few bins are booked with zero stock, as real exports sometimes are.
    if rng.random() < 0.02:
        return Decimal(0)
    return Decimal(rng.randint(*category.quantity_range)).scaleb(-quantity_decimals(category.unit))


def _batch(fake: Faker) -> str:
    return fake.bothify("L##-####")


def _comma_decimal(value: Decimal) -> str:
    return format(value, "f").replace(".", ",")
