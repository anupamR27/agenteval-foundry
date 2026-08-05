from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class FaultType(StrEnum):
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    TOOL_ERROR = "TOOL_ERROR"
    MALFORMED_OUTPUT = "MALFORMED_OUTPUT"
    BAD_RETRIEVAL = "BAD_RETRIEVAL"
    CONTEXT_TRUNCATION = "CONTEXT_TRUNCATION"


class FaultTrigger(StrEnum):
    ALWAYS = "ALWAYS"
    FIRST_CALL = "FIRST_CALL"
    CALL_NUMBER = "CALL_NUMBER"


def _is_json_safe(value: Any) -> bool:
    if value is None or isinstance(value, bool | int | float | str):
        return True
    if isinstance(value, list):
        return all(_is_json_safe(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_safe(item) for key, item in value.items())
    return False


class FaultSpec(BaseModel):
    """Deterministic fault configuration targeting one tool."""

    fault_type: FaultType
    target_tool: str
    trigger: FaultTrigger = FaultTrigger.FIRST_CALL
    call_number: int | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    fault_id: str = Field(default_factory=lambda: f"fault-{uuid4()}")
    description: str | None = None

    @field_validator("target_tool")
    @classmethod
    def target_tool_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("target_tool must not be empty")
        return value

    @field_validator("parameters")
    @classmethod
    def parameters_must_be_json_safe(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not _is_json_safe(value):
            raise ValueError("parameters must be JSON-safe")
        return value

    @model_validator(mode="after")
    def validate_call_number(self) -> "FaultSpec":
        if self.trigger == FaultTrigger.CALL_NUMBER:
            if self.call_number is None or self.call_number <= 0:
                raise ValueError("CALL_NUMBER faults require a positive call_number")
        elif self.call_number is not None:
            raise ValueError("call_number is only supported with CALL_NUMBER trigger")
        return self


class FaultActivationRecord(BaseModel):
    """Records one deterministic fault activation."""

    fault_id: str
    fault_type: FaultType
    target_tool: str
    call_number: int
    activated: bool
    reason: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
