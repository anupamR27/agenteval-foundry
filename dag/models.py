from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from evaluation.models import EvaluationEvidence, GradeResult, Verdict
from faults.models import FaultActivationRecord
from tracing.models import TraceNodeType, TraceStatus


class DagNodeStatus(StrEnum):
    HEALTHY = "HEALTHY"
    FAILED_LOCAL = "FAILED_LOCAL"
    FAILED_PROPAGATED = "FAILED_PROPAGATED"
    DISTURBANCE_HANDLED = "DISTURBANCE_HANDLED"
    UNKNOWN = "UNKNOWN"


class DagEdgeType(StrEnum):
    DEPENDENCY = "DEPENDENCY"


class EvaluationDagNode(BaseModel):
    node_id: UUID
    trace_id: UUID
    parent_ids: list[UUID] = Field(default_factory=list)
    child_ids: list[UUID] = Field(default_factory=list)
    node_type: TraceNodeType
    name: str
    execution_status: TraceStatus
    evaluation_status: DagNodeStatus = DagNodeStatus.UNKNOWN
    attached_grades: list[GradeResult] = Field(default_factory=list)
    attached_faults: list[FaultActivationRecord] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    topological_index: int | None = None


class EvaluationDagEdge(BaseModel):
    source_node_id: UUID
    target_node_id: UUID
    edge_type: DagEdgeType = DagEdgeType.DEPENDENCY
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationDAG(BaseModel):
    trace_id: UUID
    run_id: UUID | str
    nodes: list[EvaluationDagNode] = Field(default_factory=list)
    edges: list[EvaluationDagEdge] = Field(default_factory=list)
    root_node_ids: list[UUID] = Field(default_factory=list)
    unscoped_grades: list[GradeResult] = Field(default_factory=list)

    def node(self, node_id: UUID) -> EvaluationDagNode:
        for item in self.nodes:
            if item.node_id == node_id:
                return item
        raise KeyError(f"Unknown DAG node: {node_id}")

    def parents(self, node_id: UUID) -> list[EvaluationDagNode]:
        return [self.node(item) for item in self.node(node_id).parent_ids]

    def children(self, node_id: UUID) -> list[EvaluationDagNode]:
        return [self.node(item) for item in self.node(node_id).child_ids]

    def ancestors(self, node_id: UUID) -> list[EvaluationDagNode]:
        result: list[EvaluationDagNode] = []
        pending = list(self.node(node_id).parent_ids)
        seen: set[UUID] = set()
        while pending:
            current = pending.pop(0)
            if current in seen:
                continue
            seen.add(current)
            parent = self.node(current)
            result.append(parent)
            pending.extend(parent.parent_ids)
        return result


class FailureOrigin(StrEnum):
    LOCAL_ROOT = "LOCAL_ROOT"
    PROPAGATED = "PROPAGATED"
    HANDLED_DISTURBANCE = "HANDLED_DISTURBANCE"
    UNATTRIBUTED = "UNATTRIBUTED"


class RootCauseAttribution(BaseModel):
    root_node_id: UUID
    affected_node_ids: list[UUID] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    evidence: list[EvaluationEvidence] = Field(default_factory=list)
    fault_id: str | None = None
    originating_grade_names: list[str] | None = None


class RootCauseReport(BaseModel):
    run_id: UUID | str
    scenario_id: str
    overall_verdict: Verdict
    attributions: list[RootCauseAttribution] = Field(default_factory=list)
    unattributed_failed_nodes: list[UUID] = Field(default_factory=list)
    handled_disturbance_nodes: list[UUID] = Field(default_factory=list)
    unattributed_grades: list[GradeResult] = Field(default_factory=list)
    summary: str
