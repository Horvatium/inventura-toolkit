"""Jinja2 templates for the HTML pages."""

from pathlib import Path

from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from inventura.core.counting import DocumentStatus
from inventura.io.formats import format_date, format_input_quantity, format_quantity

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

STATUS_LABELS = {
    DocumentStatus.ODPRT: "Odprt",
    DocumentStatus.V_STETJU: "V štetju",
    DocumentStatus.PONOVNO_STETJE: "Ponovno štetje",
    DocumentStatus.ZAKLJUCEN: "Zaključen",
}

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
environment.globals["status_label"] = STATUS_LABELS.__getitem__
# Changes with the stylesheet, so browsers do not keep an old one after an update.
environment.globals["static_version"] = int((STATIC_DIR / "app.css").stat().st_mtime)

templates = Jinja2Templates(env=environment)
