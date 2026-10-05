"""Jinja2 templates for the HTML pages."""

from decimal import Decimal
from pathlib import Path

from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from inventura.io.formats import (
    format_date,
    format_decimal,
    format_input_quantity,
    format_quantity,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

environment = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)
environment.filters["quantity"] = format_quantity
environment.filters["input_quantity"] = format_input_quantity
environment.filters["date"] = format_date
environment.filters["number"] = lambda value: format_decimal(Decimal(value), 0)
environment.filters["euro"] = lambda value: format_decimal(value, 2) + " €"
environment.filters["money"] = lambda value: (
    ("+" if value > 0 else "") + format_decimal(value, 2) + " €"
)
environment.filters["percent"] = lambda value: (
    "–" if value is None else ("+" if value > 0 else "") + format_decimal(value, 1) + " %"
)
# Changes with any static file, so browsers do not keep an old one after an update.
environment.globals["static_version"] = int(
    max(path.stat().st_mtime for path in STATIC_DIR.iterdir() if path.is_file())
)

FIELD_LABELS = {
    "sifra": "Šifra",
    "opis": "Opis",
    "merska_enota": "ME",
    "lokacija": "Lokacija",
    "sarza": "Šarža",
    "kolicina": "Zaloga",
    "cena_na_enoto": "Cena",
    "presteta_kolicina": "Prešteta količina",
}
environment.filters["field_label"] = lambda field: FIELD_LABELS.get(field or "", field or "")

templates = Jinja2Templates(env=environment)
