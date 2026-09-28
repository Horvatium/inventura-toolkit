"""Command line interface: ``inventura generate`` and ``inventura import``."""

from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError

from inventura import generator
from inventura.io.column_mapping import ColumnMappingError, load_column_mapping
from inventura.io.importer import UnsupportedFileError, import_stock_file, write_error_report

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
        raise typer.BadParameter("output must end in .csv or .xlsx", param_hint="--output")
    rows = generator.generate_stock(materials=materials, seed=seed)
    output.parent.mkdir(parents=True, exist_ok=True)
    if suffix == ".csv":
        generator.write_csv(rows, output)
    else:
        generator.write_xlsx(rows, output)
    typer.echo(f"Wrote {len(rows)} rows for {materials} materials to {output}")


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
    try:
        column_mapping = load_column_mapping(mapping)
    except ValidationError as exc:
        _fail(f"Invalid column mapping {mapping}:\n{exc}")
    try:
        report = import_stock_file(file, column_mapping)
    except (ColumnMappingError, UnsupportedFileError, UnicodeDecodeError) as exc:
        _fail(f"Cannot import {file}: {exc}")

    result = report.result
    typer.echo(f"File: {file}")
    typer.echo("Columns: " + ", ".join(f"{f} <- {h!r}" for f, h in report.columns.items()))
    typer.echo(
        f"Rows: {report.data_rows} read, {len(result.rows)} valid, "
        f"{result.error_row_count} with errors, {result.skipped_blank_rows} blank skipped"
    )
    if result.is_valid:
        typer.echo("No errors.")
        return

    typer.echo(f"Errors: {len(result.errors)}")
    for error in result.errors[:show]:
        field = error.field or "-"
        typer.echo(f"  row {error.row_number:>6}  {field:<14} {error.value!r:<20} {error.message}")
    if len(result.errors) > show:
        typer.echo(f"  ... {len(result.errors) - show} more")
    if errors_csv is not None:
        write_error_report(result.errors, errors_csv)
        typer.echo(f"Error report written to {errors_csv}")
    raise typer.Exit(code=1)


def _fail(message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(code=2)
