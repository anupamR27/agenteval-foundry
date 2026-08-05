from datetime import UTC, datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aut.base import AgentResult
from dag.models import EvaluationDAG, RootCauseReport
from evaluation.models import EvaluationReport
from evaluation.taxonomy.models import FailureClassificationReport
from faults.models import FaultActivationRecord
from scenarios.models import Scenario
from tracing.models import ExecutionTrace


class RunBundle(BaseModel):
    """Immutable canonical snapshot of one completed evaluation pipeline."""

    model_config = ConfigDict(frozen=True)

    run_id: UUID | str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    scenario: Scenario
    agent_result: AgentResult
    execution_trace: ExecutionTrace
    fault_activation_records: tuple[FaultActivationRecord, ...] = ()
    evaluation_report: EvaluationReport
    evaluation_dag: EvaluationDAG
    root_cause_report: RootCauseReport
    failure_classification_report: FailureClassificationReport
    agent_name: str
    agent_version: str
    schema_version: str = "1.0"

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_run_identity(self) -> Self:
        expected = str(self.run_id)
        observed = {
            str(self.execution_trace.run_id),
            str(self.evaluation_report.run_id),
            str(self.evaluation_dag.run_id),
            str(self.root_cause_report.run_id),
            str(self.failure_classification_report.run_id),
        }
        if observed != {expected}:
            raise ValueError(
                f"RunBundle contains inconsistent run IDs: expected {expected}, got {observed}"
            )
        return self

    @classmethod
    def from_pipeline(
        cls,
        *,
        scenario: Scenario,
        agent_result: AgentResult,
        execution_trace: ExecutionTrace,
        fault_activation_records: tuple[FaultActivationRecord, ...],
        evaluation_report: EvaluationReport,
        evaluation_dag: EvaluationDAG,
        root_cause_report: RootCauseReport,
        failure_classification_report: FailureClassificationReport,
        created_at: datetime | None = None,
    ) -> "RunBundle":
        data = {
            "run_id": execution_trace.run_id,
            "created_at": created_at or datetime.now(UTC),
            "scenario": scenario.model_dump(mode="json"),
            "agent_result": agent_result.model_dump(mode="json"),
            "execution_trace": execution_trace.model_dump(mode="json"),
            "fault_activation_records": [
                record.model_dump(mode="json") for record in fault_activation_records
            ],
            "evaluation_report": evaluation_report.model_dump(mode="json"),
            "evaluation_dag": evaluation_dag.model_dump(mode="json"),
            "root_cause_report": root_cause_report.model_dump(mode="json"),
            "failure_classification_report": failure_classification_report.model_dump(mode="json"),
            "agent_name": agent_result.agent_metadata.name,
            "agent_version": agent_result.agent_metadata.version,
            "schema_version": "1.0",
        }
        return cls.model_validate(data)
