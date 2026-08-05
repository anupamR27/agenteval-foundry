"""Create evaluation run persistence tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260805_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("scenario_id", sa.String(255), nullable=False),
        sa.Column("scenario_version", sa.Integer(), nullable=False),
        sa.Column("agent_name", sa.String(255), nullable=False),
        sa.Column("agent_version", sa.String(64), nullable=False),
        sa.Column("overall_verdict", sa.String(32), nullable=False),
        sa.Column("taxonomy_version", sa.String(32), nullable=False),
        sa.Column("root_cause_count", sa.Integer(), nullable=False),
        sa.Column("classification_count", sa.Integer(), nullable=False),
        sa.Column("bundle_json", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_runs_created_at", "runs", ["created_at"])
    op.create_index("ix_runs_scenario_id", "runs", ["scenario_id"])
    op.create_index("ix_runs_overall_verdict", "runs", ["overall_verdict"])

    op.create_table(
        "trace_spans",
        sa.Column("span_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("runs.run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("parent_span_id", postgresql.UUID(as_uuid=True)),
        sa.Column("node_type", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("latency_ms", sa.Float()),
        sa.Column("input_data", postgresql.JSONB(), nullable=False),
        sa.Column("output_data", postgresql.JSONB(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_index("ix_trace_spans_run_id", "trace_spans", ["run_id"])

    op.create_table(
        "grade_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("runs.run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_span_id", postgresql.UUID(as_uuid=True)),
        sa.Column("grader_name", sa.String(255), nullable=False),
        sa.Column("grader_version", sa.String(64), nullable=False),
        sa.Column("evaluation_level", sa.String(32), nullable=False),
        sa.Column("verdict", sa.String(32), nullable=False),
        sa.Column("score", sa.Float()),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_index("ix_grade_results_run_id", "grade_results", ["run_id"])
    op.create_index("ix_grade_results_verdict", "grade_results", ["verdict"])

    op.create_table(
        "fault_activations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("runs.run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fault_id", sa.String(255), nullable=False),
        sa.Column("fault_type", sa.String(64), nullable=False),
        sa.Column("target_tool", sa.String(255), nullable=False),
        sa.Column("call_number", sa.Integer(), nullable=False),
        sa.Column("activated", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_index("ix_fault_activations_run_id", "fault_activations", ["run_id"])


def downgrade() -> None:
    op.drop_table("fault_activations")
    op.drop_table("grade_results")
    op.drop_table("trace_spans")
    op.drop_table("runs")
