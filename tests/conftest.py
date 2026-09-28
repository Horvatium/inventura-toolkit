from pathlib import Path

import pytest

from inventura.io.column_mapping import ColumnMapping, load_column_mapping

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def mapping_path() -> Path:
    return REPO_ROOT / "config" / "column_mapping.yaml"


@pytest.fixture(scope="session")
def mapping(mapping_path: Path) -> ColumnMapping:
    return load_column_mapping(mapping_path)


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return REPO_ROOT / "tests" / "fixtures"
