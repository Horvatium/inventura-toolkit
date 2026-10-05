from pathlib import Path

import pytest
from typer.testing import CliRunner

from inventura.cli import app

runner = CliRunner()


def test_generate_and_import_csv(tmp_path: Path, mapping_path: Path) -> None:
    output = tmp_path / "out" / "stock.csv"
    result = runner.invoke(app, ["generate", "-o", str(output), "--materials", "30"])
    assert result.exit_code == 0, result.output
    assert "materialov: 30" in result.output

    result = runner.invoke(app, ["import", str(output), "--mapping", str(mapping_path)])
    assert result.exit_code == 0, result.output
    assert "Brez napak." in result.output


def test_generate_xlsx(tmp_path: Path) -> None:
    output = tmp_path / "stock.xlsx"
    result = runner.invoke(app, ["generate", "-o", str(output), "--materials", "5"])
    assert result.exit_code == 0, result.output
    assert output.exists()


def test_generate_rejects_other_suffix(tmp_path: Path) -> None:
    result = runner.invoke(app, ["generate", "-o", str(tmp_path / "stock.json")])
    assert result.exit_code == 2


def test_import_with_errors_exits_1_and_writes_report(
    tmp_path: Path, mapping_path: Path, fixtures_dir: Path
) -> None:
    report = tmp_path / "errors.csv"
    result = runner.invoke(
        app,
        [
            "import",
            str(fixtures_dir / "stock_errors.csv"),
            "--mapping",
            str(mapping_path),
            "--errors-csv",
            str(report),
            "--show",
            "3",
        ],
    )
    assert result.exit_code == 1
    assert "veljavnih 2, z napakami 10, praznih 2" in result.output
    assert "... in še 7" in result.output
    assert report.exists()


def test_import_missing_columns_exits_2(tmp_path: Path, mapping_path: Path) -> None:
    path = tmp_path / "stock.csv"
    path.write_text("A;B\n1;2\n", encoding="utf-8")
    result = runner.invoke(app, ["import", str(path), "--mapping", str(mapping_path)])
    assert result.exit_code == 2
    assert "manjkajo stolpci" in result.output


def test_import_invalid_mapping_exits_2(tmp_path: Path, fixtures_dir: Path) -> None:
    mapping = tmp_path / "mapping.yaml"
    mapping.write_text("columns: {}\n", encoding="utf-8")
    result = runner.invoke(
        app, ["import", str(fixtures_dir / "stock_errors.csv"), "--mapping", str(mapping)]
    )
    assert result.exit_code == 2
    assert "Neveljavna preslikava stolpcev" in result.output


def test_sheets_writes_xlsx_and_html(tmp_path: Path, mapping_path: Path) -> None:
    export = tmp_path / "stock.csv"
    runner.invoke(app, ["generate", "-o", str(export), "--materials", "40"])
    out = tmp_path / "sheets"
    result = runner.invoke(
        app,
        [
            "sheets",
            str(export),
            "-o",
            str(out),
            "--date",
            "2026-09-28",
            "--mapping",
            str(mapping_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (out / "count_sheets.xlsx").exists()
    html = (out / "count_sheets.html").read_text(encoding="utf-8")
    assert "Datum: 28. 9. 2026" in html
    assert "Popisni listi (12 od 12)" in result.output


def test_sheets_for_selected_racks(tmp_path: Path, mapping_path: Path) -> None:
    export = tmp_path / "stock.csv"
    runner.invoke(app, ["generate", "-o", str(export), "--materials", "200"])
    out = tmp_path / "sheets"
    args = ["sheets", str(export), "-o", str(out), "--mapping", str(mapping_path)]
    result = runner.invoke(app, [*args, "-r", "k2", "-r", "B06"])
    assert result.exit_code == 0, result.output
    assert "Popisni listi (2 od 12)" in result.output
    html = (out / "count_sheets.html").read_text(encoding="utf-8")
    assert html.index("regal B6") < html.index("regal K2")


@pytest.mark.parametrize(
    ("rack", "message"), [("B99", "v regalu B99 ni zaloge"), ("6B", "neveljaven regal")]
)
def test_sheets_rejects_unknown_rack(
    tmp_path: Path, mapping_path: Path, fixtures_dir: Path, rack: str, message: str
) -> None:
    result = runner.invoke(
        app,
        [
            "sheets",
            str(fixtures_dir / "stock_english_headers.csv"),
            "-o",
            str(tmp_path),
            "-r",
            rack,
            "--mapping",
            str(mapping_path),
        ],
    )
    assert result.exit_code == 2
    assert message in result.output


def test_sheets_refuses_export_with_errors(
    tmp_path: Path, mapping_path: Path, fixtures_dir: Path
) -> None:
    out = tmp_path / "sheets"
    result = runner.invoke(
        app,
        [
            "sheets",
            str(fixtures_dir / "stock_errors.csv"),
            "-o",
            str(out),
            "--mapping",
            str(mapping_path),
        ],
    )
    assert result.exit_code == 1
    assert "popravi zgornje napake" in result.output
    assert not out.exists()
