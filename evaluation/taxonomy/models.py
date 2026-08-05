from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from evaluation.models import EvaluationEvidence


class TaxonomyLevel3(BaseModel):
    identifier: str
    description: str
    remediation_hints: list[str] = Field(default_factory=list)


class TaxonomyLevel2(BaseModel):
    identifier: str
    description: str
    categories: list[TaxonomyLevel3] = Field(default_factory=list)


class TaxonomyLevel1(BaseModel):
    identifier: str
    description: str
    categories: list[TaxonomyLevel2] = Field(default_factory=list)


class FailureTaxonomyDefinition(BaseModel):
    name: str
    version: str
    description: str
    categories: list[TaxonomyLevel1] = Field(default_factory=list)


class FailureTaxonomyPath(BaseModel):
    level1: str
    level2: str
    level3: str
    taxonomy_version: str
    description: str | None = None

    @property
    def identifiers(self) -> tuple[str, str, str]:
        return self.level1, self.level2, self.level3


class ClassificationConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ClassificationSource(StrEnum):
    DETERMINISTIC_FAULT = "DETERMINISTIC_FAULT"
    DETERMINISTIC_GRADE = "DETERMINISTIC_GRADE"
    TRACE_STRUCTURE = "TRACE_STRUCTURE"
    HEURISTIC = "HEURISTIC"
    UNKNOWN = "UNKNOWN"


class FailureClassification(BaseModel):
    classification_id: UUID = Field(default_factory=uuid4)
    root_node_id: UUID
    taxonomy_path: FailureTaxonomyPath
    confidence: ClassificationConfidence
    confidence_score: float = Field(ge=0.0, le=1.0)
    reason: str
    evidence: list[EvaluationEvidence] = Field(default_factory=list)
    source: ClassificationSource
    fault_id: str | None = None
    affected_node_ids: list[UUID] = Field(default_factory=list)
    alternative_paths: list[FailureTaxonomyPath] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FailureClassificationReport(BaseModel):
    run_id: UUID | str
    scenario_id: str
    taxonomy_version: str
    classifications: list[FailureClassification] = Field(default_factory=list)
    unclassified_root_nodes: list[UUID] = Field(default_factory=list)
    ambiguous_root_nodes: list[UUID] = Field(default_factory=list)
    summary: str
