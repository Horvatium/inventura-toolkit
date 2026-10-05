"""Load the recount rules from config/variance_rules.yaml."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from inventura.core.variance import VarianceRules


class _RulesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_rounds: int = Field(ge=1)


def load_variance_rules(path: Path) -> VarianceRules:
    with path.open(encoding="utf-8") as file:
        # BaseLoader keeps every scalar as text; pydantic then checks and converts it.
        data = yaml.load(file, Loader=yaml.BaseLoader)
    rules = _RulesFile.model_validate(data)
    return VarianceRules(max_rounds=rules.max_rounds)
