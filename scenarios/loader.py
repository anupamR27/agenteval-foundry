# Take a YAML text file
#         ↓
# Read it
#         ↓
# Convert it into Python data | Parsing and Tokenization: The function takes your YAML text
#                                and breaks it down into standard tokens
#         ↓
# Validate it
#         ↓
# Return a proper Scenario object

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

    with path.open("r", encoding="utf-8") as file: #UTF-8 is the standard encoding, Without this special characters can become garbage
        payload: Any = yaml.safe_load(file) #safe_load -> convers yaml to understandable python stuff
        # Payload = actual useful data

    if not isinstance(payload, dict):
        raise TypeError(
            f"Scenario must contain a YAML object, received: {type(payload).__name__}"
        )

    return Scenario.model_validate(payload) # compare the dict with the blueprint
