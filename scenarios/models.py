from typing import Any

from pydantic import BaseModel, Field


class ExpectedBehavior(BaseModel):
    required_tools: list[str] = Field(default_factory=list)
    required_claims: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)


class Scenario(BaseModel):
    id: str
    version: int = 1
    name: str
    query: str
    expected: ExpectedBehavior
    fault_profile: dict[str, Any] | None = None

