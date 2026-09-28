from pathlib import Path

from typer.testing import CliRunner

from inventura.cli import app

runner = CliRunner()


def test_generate_and_import_csv(tmp_path: Path, mapping_path: Path) -> None:
    output = tmp_path / "out" / "stock.csv"
    result = runner.invoke(app, ["generate", "-o", str(output), "--materials", "30"])
    assert result.exit_code == 0, result.output
    assert "for 30 materials" in result.output

    result = runner.invoke(app, ["import", str(output), "--mapping", str(mapping_path)])
    assert result.exit_code == 0, result.output
    assert "No errors." in result.output


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
    assert "2 valid, 7 with errors, 2 blank skipped" in result.output
    assert "... 4 more" in result.output
    assert report.exists()


def test_import_missing_columns_exits_2(tmp_path: Path, mapping_path: Path) -> None:
    path = tmp_path / "stock.csv"
    path.write_text("A;B\n1;2\n", encoding="utf-8")
    result = runner.invoke(app, ["import", str(path), "--mapping", str(mapping_path)])
    assert result.exit_code == 2
    assert "missing columns" in result.output


def test_import_invalid_mapping_exits_2(tmp_path: Path, fixtures_dir: Path) -> None:
    mapping = tmp_path / "mapping.yaml"
    mapping.write_text("columns: {}\n", encoding="utf-8")
    result = runner.invoke(
        app, ["import", str(fixtures_dir / "stock_errors.csv"), "--mapping", str(mapping)]
    )
    assert result.exit_code == 2
    assert "Invalid column mapping" in result.output
