from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TraceNodeType(StrEnum):
    AGENT_EXECUTION = "AGENT_EXECUTION"
    TOOL_EXECUTION = "TOOL_EXECUTION"
    SYNTHESIS = "SYNTHESIS"


class TraceStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class TraceSpan(BaseModel):
    """One timed execution span in an in-memory trace."""

    span_id: UUID = Field(default_factory=uuid4)
    trace_id: UUID
    parent_span_id: UUID | None = None
    node_type: TraceNodeType
    name: str
    started_at: datetime
    ended_at: datetime | None = None
    latency_ms: float | None = None
    status: TraceStatus = TraceStatus.RUNNING
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionTrace(BaseModel):
    """Ordered collection of spans for one agent run."""

    trace_id: UUID = Field(default_factory=uuid4)
    run_id: UUID | str
    spans: list[TraceSpan] = Field(default_factory=list)

    def spans_by_type(self, node_type: TraceNodeType) -> list[TraceSpan]:
        return [span for span in self.spans if span.node_type == node_type]
