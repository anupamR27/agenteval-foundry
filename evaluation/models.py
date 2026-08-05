from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    ERROR = "ERROR"


class EvaluationLevel(StrEnum):
    STEP = "STEP"
    RUN = "RUN"


class EvaluationEvidence(BaseModel):
    assertion: str
    expected: Any
    observed: Any
    message: str | None = None
    span_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GradeResult(BaseModel):
    grader_name: str
    grader_version: str
    level: EvaluationLevel
    verdict: Verdict
    score: float | None = None
    target_span_id: UUID | None = None
    summary: str
    evidence: list[EvaluationEvidence] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationReport(BaseModel):
    run_id: UUID | str
    scenario_id: str
    scenario_version: int
    overall_verdict: Verdict
    grades: list[GradeResult] = Field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0
    inconclusive_count: int = 0
    error_count: int = 0
    summary: str | None = None
