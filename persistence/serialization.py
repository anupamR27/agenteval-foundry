import json
from typing import Any

from pydantic import ValidationError
from pydantic_core import PydanticSerializationError

from persistence.models import RunBundle


class RunSerializationError(ValueError):
    pass


_SECRET_KEYS = {"api_key", "database_url", "groq_api_key", "password", "secret"}


def _reject_secret_keys(value: Any, path: str = "bundle") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).casefold() in _SECRET_KEYS:
                raise RunSerializationError(f"Secret-bearing field is not persistable: {path}.{key}")
            _reject_secret_keys(item, f"{path}.{key}")
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            _reject_secret_keys(item, f"{path}[{index}]")


def bundle_to_dict(bundle: RunBundle) -> dict[str, Any]:
    try:
        data = bundle.model_dump(mode="json")
        _reject_secret_keys(data)
        json.dumps(data, allow_nan=False, sort_keys=True)
    except (PydanticSerializationError, TypeError, ValueError) as exc:
        if isinstance(exc, RunSerializationError):
            raise
        raise RunSerializationError(f"RunBundle contains unsupported JSON data: {exc}") from exc
    return data


def bundle_from_dict(data: dict[str, Any]) -> RunBundle:
    try:
        return RunBundle.model_validate(data)
    except (ValidationError, TypeError, ValueError) as exc:
        raise RunSerializationError(f"Malformed RunBundle data: {exc}") from exc


def bundle_to_json(bundle: RunBundle) -> str:
    return json.dumps(
        bundle_to_dict(bundle),
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def bundle_from_json(value: str) -> RunBundle:
    try:
        data = json.loads(value)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RunSerializationError(f"Malformed RunBundle JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RunSerializationError("Malformed RunBundle JSON: root value must be an object")
    return bundle_from_dict(data)
