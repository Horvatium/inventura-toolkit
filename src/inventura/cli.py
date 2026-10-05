"""Command line interface: ``inventura generate``, ``import``, ``sheets`` and ``serve``."""

from datetime import date, datetime
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError

from inventura import generator
from inventura.core.documents import split_by_rack
from inventura.core.locations import LocationError, rack_sort_key
from inventura.io.column_mapping import ColumnMappingError, load_column_mapping
from inventura.io.count_sheets import (
    SheetOptions,
    write_count_sheets_html,
    write_count_sheets_xlsx,
)
from inventura.io.formats import format_decimal
from inventura.io.importer import (
    ImportReport,
    UnreadableFileError,
    UnsupportedFileError,
    import_stock_file,
    write_error_report,
)

DEFAULT_MAPPING = Path("config/column_mapping.yaml")

app = typer.Typer(help="Warehouse stock count toolkit.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Warehouse stock count toolkit."""


@app.command()
def generate(
    output: Annotated[
        Path, typer.Option("--output", "-o", help="Target file, .csv or .xlsx.")
    ] = Path("sample_data/stock_export.csv"),
    materials: Annotated[int, typer.Option(min=1, help="Number of materials.")] = 2000,
    seed: Annotated[int, typer.Option(help="Random seed; the same seed gives the same data.")] = 42,
) -> None:
    """Generate a fictional stock export."""
    suffix = output.suffix.lower()
    if suffix not in (".csv", ".xlsx"):
        raise typer.BadParameter(
            "datoteka mora imeti končnico .csv ali .xlsx", param_hint="--output"
        )
    rows = generator.generate_stock(materials=materials, seed=seed)
    output.parent.mkdir(parents=True, exist_ok=True)
    if suffix == ".csv":
        generator.write_csv(rows, output)
    else:
        generator.write_xlsx(rows, output)
    typer.echo(f"Izvoz zalog: {output} (materialov: {materials}, vrstic: {len(rows)})")


@app.command("import")
def import_stock(
    file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="CSV or XLSX export.")],
    mapping: Annotated[
        Path, typer.Option(exists=True, dir_okay=False, help="Column mapping YAML.")
    ] = DEFAULT_MAPPING,
    errors_csv: Annotated[
        Path | None, typer.Option(help="Write all row errors to this CSV file.")
    ] = None,
    show: Annotated[int, typer.Option(min=0, help="Row errors to print.")] = 20,
) -> None:
    """Read and validate a stock export and report errors by row.

    Exits with code 1 if any row is invalid, 2 if the file cannot be read at all.
    """
    report = _import(file, mapping, errors_csv, show)
    if not report.result.is_valid:
        raise typer.Exit(code=1)
    typer.echo("Brez napak.")


@app.command()
def sheets(
    file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="CSV or XLSX export.")],
    output_dir: Annotated[
        Path, typer.Option("--output-dir", "-o", file_okay=False, help="Where to write sheets.")
    ] = Path("output"),
    rack: Annotated[
        list[str] | None, typer.Option("--rack", "-r", help="Only these racks, e.g. -r B6 -r K2.")
    ] = None,
    book_quantities: Annotated[
        bool, typer.Option(help="Print book quantities (default: blind count).")
    ] = False,
    created: Annotated[
        datetime | None, typer.Option("--date", formats=["%Y-%m-%d"], help="Date on the sheets.")
    ] = None,
    mapping: Annotated[
        Path, typer.Option(exists=True, dir_okay=False, help="Column mapping YAML.")
    ] = DEFAULT_MAPPING,
) -> None:
    """Split a stock export into one count document per rack and write count sheets.

    Writes count_sheets.xlsx (one worksheet per rack) and count_sheets.html (for printing).
    Nothing is written if the export has row errors.
    """
    report = _import(file, mapping, errors_csv=None, show=20)
    if not report.result.is_valid:
        typer.echo("Pred pripravo popisnih listov popravi zgornje napake.", err=True)
        raise typer.Exit(code=1)

    documents = split_by_rack(report.result.rows)
    selected = documents
    if rack:
        try:
            wanted = {rack_sort_key(name) for name in rack}
        except LocationError as exc:
            raise typer.BadParameter(str(exc), param_hint="--rack") from exc
        selected = [d for d in documents if rack_sort_key(d.rack) in wanted]
        missing = wanted - {rack_sort_key(d.rack) for d in selected}
        if missing:
            names = ", ".join(f"{prefix}{number}" for prefix, number in sorted(missing))
            raise typer.BadParameter(f"v regalu {names} ni zaloge", param_hint="--rack")

    options = SheetOptions(
        created=(created.date() if created else date.today()),
        total_documents=len(documents),
        show_book_quantity=book_quantities,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = output_dir / "count_sheets.xlsx"
    html_path = output_dir / "count_sheets.html"
    write_count_sheets_xlsx(selected, xlsx_path, options)
    write_count_sheets_html(selected, html_path, options)

    for document in selected:
        typer.echo(
            f"  {document.number:>3}. regal {document.rack:<5} postavk: {len(document.items):>5}  "
            f"lokacij: {len(document.locations):>4}  "
            f"knjižna vrednost: {format_decimal(document.book_value, 2):>13} €"
        )
    typer.echo(f"Popisni listi ({len(selected)} od {len(documents)}): {xlsx_path}")
    typer.echo(f"Stran za tisk: {html_path}")


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Interface to listen on.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to listen on.")] = 8000,
    reload: Annotated[bool, typer.Option(help="Restart on code changes.")] = False,
) -> None:
    """Run the web application (API docs at /docs)."""
    import uvicorn

    uvicorn.run("inventura.web.app:create_app", factory=True, host=host, port=port, reload=reload)


def _import(file: Path, mapping: Path, errors_csv: Path | None, show: int) -> ImportReport:
    """Import and print a summary with the first row errors; exit 2 if the file is unreadable."""
    try:
        column_mapping = load_column_mapping(mapping)
    except ValidationError as exc:
        _fail(f"Neveljavna preslikava stolpcev {mapping}:\n{exc}")
    try:
        report = import_stock_file(file, column_mapping)
    except (ColumnMappingError, UnsupportedFileError, UnreadableFileError) as exc:
        _fail(f"Datoteke {file} ni mogoče uvoziti: {exc}")

    result = report.result
    typer.echo(f"Datoteka: {file}")
    typer.echo("Stolpci: " + ", ".join(f"{f} <- {h!r}" for f, h in report.columns.items()))
    typer.echo(
        f"Vrstice: prebranih {report.data_rows}, veljavnih {len(result.rows)}, "
        f"z napakami {result.error_row_count}, praznih {result.skipped_blank_rows}"
    )
    if result.is_valid:
        return report

    typer.echo(f"Napake: {len(result.errors)}")
    for error in result.errors[:show]:
        field = error.field or "-"
        typer.echo(
            f"  vrstica {error.row_number:>6}  {field:<14} {error.value!r:<20} {error.message}"
        )
    if len(result.errors) > show:
        typer.echo(f"  ... in še {len(result.errors) - show}")
    if errors_csv is not None:
        write_error_report(result.errors, errors_csv)
        typer.echo(f"Poročilo o napakah: {errors_csv}")
    return report


def _fail(message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(code=2)
