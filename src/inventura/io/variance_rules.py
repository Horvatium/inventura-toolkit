"""Load the recount rules from config/variance_rules.yaml."""

from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from inventura.core.variance import VarianceRules


class _RulesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_value: Decimal = Field(ge=0)
    min_percent: Decimal = Field(ge=0)
    always_value: Decimal = Field(ge=0)
    max_rounds: int = Field(ge=1)


def load_variance_rules(path: Path) -> VarianceRules:
    with path.open(encoding="utf-8") as file:
        # BaseLoader keeps every scalar as text, so 50.00 becomes Decimal("50.00"), not a float.
        data = yaml.load(file, Loader=yaml.BaseLoader)
    rules = _RulesFile.model_validate(data)
    return VarianceRules(
        min_value=rules.min_value,
        min_percent=rules.min_percent,
        always_value=rules.always_value,
        max_rounds=rules.max_rounds,
    )
