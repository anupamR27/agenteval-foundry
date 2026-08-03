from pathlib import Path
from typing import Any

import yaml

from scenarios.models import Scenario


def load_scenario(path: Path) -> Scenario:
    """Load and validate one evaluation scenario from YAML."""

    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")

    if not path.is_file():
        raise ValueError(f"Scenario path is not a file: {path}")

    with path.open("r", encoding="utf-8") as file:
        payload: Any = yaml.safe_load(file)

    if not isinstance(payload, dict):
        raise ValueError(
            f"Scenario must contain a YAML object, received: {type(payload).__name__}"
        )

    return Scenario.model_validate(payload)