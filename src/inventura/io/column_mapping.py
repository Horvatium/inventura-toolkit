"""Column mapping configuration (config/column_mapping.yaml) and header resolution."""

from collections.abc import Sequence
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from inventura.core.numbers import NumberFormat
from inventura.core.stock import REQUIRED_FIELDS, StockField


class ColumnMappingError(ValueError):
    """The headers of a file cannot be matched to the required fields."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NumberOptions(_Model):
    decimal_separator: str = ","
    thousands_separator: str | None = "."

    def to_format(self) -> NumberFormat:
        return NumberFormat(self.decimal_separator, self.thousands_separator)

    @model_validator(mode="after")
    def _check_separators(self) -> Self:
        self.to_format()
        return self


class CsvOptions(_Model):
    delimiter: str = Field(default=";", min_length=1, max_length=1)
    encoding: str = "utf-8-sig"


class XlsxOptions(_Model):
    sheet: int | str = 0


class ColumnMapping(_Model):
    columns: dict[StockField, list[str]]
    numbers: NumberOptions = NumberOptions()
    csv: CsvOptions = CsvOptions()
    xlsx: XlsxOptions = XlsxOptions()

    @model_validator(mode="after")
    def _check_columns(self) -> Self:
        missing = sorted(REQUIRED_FIELDS - self.columns.keys())
        if missing:
            raise ValueError(f"no headers configured for: {', '.join(missing)}")
        owner: dict[str, StockField] = {}
        for field, headers in self.columns.items():
            if not headers:
                raise ValueError(f"field {field} has an empty header list")
            for header in headers:
                key = _normalise(header)
                if not key:
                    raise ValueError(f"field {field} has a blank header")
                if key in owner and owner[key] != field:
                    raise ValueError(f"header {header!r} is used by {owner[key]} and {field}")
                owner[key] = field
        return self

    def resolve(self, headers: Sequence[str]) -> dict[StockField, str]:
        """Match the headers of a file to fields; returns field -> header as found in the file."""
        by_key = {
            _normalise(header): field for field, names in self.columns.items() for header in names
        }
        found: dict[StockField, list[str]] = {}
        for header in headers:
            field = by_key.get(_normalise(header))
            if field is not None:
                found.setdefault(field, []).append(header)

        problems = []
        missing = sorted(REQUIRED_FIELDS - found.keys())
        if missing:
            problems.append(
                "missing columns: "
                + "; ".join(f"{field} (one of {self.columns[field]})" for field in missing)
            )
        for field, matches in found.items():
            if len(matches) > 1:
                problems.append(f"several columns match {field}: {matches}")
        if problems:
            raise ColumnMappingError(". ".join(problems) + f". Headers in file: {list(headers)}")
        return {field: matches[0] for field, matches in found.items()}


def load_column_mapping(path: Path) -> ColumnMapping:
    with path.open(encoding="utf-8") as file:
        data = yaml.safe_load(file)
    return ColumnMapping.model_validate(data)


def _normalise(header: str) -> str:
    return " ".join(str(header).split()).casefold()
