from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import Mapped, mapped_column

from persistence.postgres.base import Base


class RunRecord(Base):
    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_created_at", "created_at"),
        Index("ix_runs_scenario_id", "scenario_id"),
        Index("ix_runs_overall_verdict", "overall_verdict"),
    )

    run_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    scenario_id: Mapped[str] = mapped_column(String(255), nullable=False)
    scenario_version: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_name: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(64), nullable=False)
    overall_verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    taxonomy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    root_cause_count: Mapped[int] = mapped_column(Integer, nullable=False)
    classification_count: Mapped[int] = mapped_column(Integer, nullable=False)
    bundle_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class TraceSpanRecord(Base):
    __tablename__ = "trace_spans"
    __table_args__ = (Index("ix_trace_spans_run_id", "run_id"),)

    span_id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_span_id: Mapped[UUID | None] = mapped_column(PostgresUUID(as_uuid=True))
    node_type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[float | None] = mapped_column(Float)
    input_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class GradeResultRecord(Base):
    __tablename__ = "grade_results"
    __table_args__ = (
        Index("ix_grade_results_run_id", "run_id"),
        Index("ix_grade_results_verdict", "verdict"),
    )

    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    target_span_id: Mapped[UUID | None] = mapped_column(PostgresUUID(as_uuid=True))
    grader_name: Mapped[str] = mapped_column(String(255), nullable=False)
    grader_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_level: Mapped[str] = mapped_column(String(32), nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class FaultActivationRecordRow(Base):
    __tablename__ = "fault_activations"
    __table_args__ = (Index("ix_fault_activations_run_id", "run_id"),)

    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    fault_id: Mapped[str] = mapped_column(String(255), nullable=False)
    fault_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_tool: Mapped[str] = mapped_column(String(255), nullable=False)
    call_number: Mapped[int] = mapped_column(Integer, nullable=False)
    activated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
