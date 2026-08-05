from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from faults.models import FaultSpec


class ResponseMode(StrEnum):
    ANSWER = "ANSWER"
    SAFE_FAILURE = "SAFE_FAILURE"
    INCOMPLETE_INFORMATION = "INCOMPLETE_INFORMATION"
    INVALID_DATA = "INVALID_DATA"


class ToolOutcomeExpectation(BaseModel):
    tool_name: str
    expected_success: bool
    expected_error_contains: str | None = None
    expected_call_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def error_expectation_requires_failure(self) -> "ToolOutcomeExpectation":
        if self.expected_error_contains is not None and self.expected_success:
            raise ValueError("expected_error_contains requires expected_success=false")
        return self


class ResponseExpectation(BaseModel):
    mode: ResponseMode
    required_markers: list[str] = Field(default_factory=list)
    forbidden_markers: list[str] = Field(default_factory=list)


class ExpectedBehavior(BaseModel):
    required_tools: list[str] = Field(default_factory=list)
    required_claims: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    tool_outcomes: list[ToolOutcomeExpectation] = Field(default_factory=list)
    response: ResponseExpectation | None = None


class Scenario(BaseModel):
    id: str
    version: int = 1
    name: str
    query: str
    expected: ExpectedBehavior
    fault_profile: list[FaultSpec] | None = None
