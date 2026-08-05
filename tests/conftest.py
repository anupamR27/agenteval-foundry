from datetime import UTC, datetime
from uuid import uuid4

import pytest

from aut.base import AgentMetadata, AgentResult, ToolCallRecord
from evaluation.context import EvaluationContext
from scenarios.models import ExpectedBehavior, Scenario
from tracing.models import ExecutionTrace, TraceNodeType, TraceSpan, TraceStatus


def completed_span(node_type, name, trace_id, parent_span_id=None, status=TraceStatus.SUCCESS):
    now = datetime.now(UTC)
    return TraceSpan(
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        node_type=node_type,
        name=name,
        started_at=now,
        ended_at=now,
        latency_ms=0.0,
        status=status,
    )


@pytest.fixture
def evaluation_context() -> EvaluationContext:
    trace_id = uuid4()
    root = completed_span(TraceNodeType.AGENT_EXECUTION, "agent", trace_id)
    tool = completed_span(TraceNodeType.TOOL_EXECUTION, "search_policy", trace_id, root.span_id)
    synthesis = completed_span(TraceNodeType.SYNTHESIS, "synthesis", trace_id, root.span_id)
    return EvaluationContext(
        scenario=Scenario(
            id="test",
            name="test",
            query="query",
            expected=ExpectedBehavior(required_tools=["search_policy"]),
        ),
        agent_result=AgentResult(
            answer="Refunds are available within 14 days.",
            agent_metadata=AgentMetadata(name="test", version="1"),
            tool_calls=[ToolCallRecord(
                tool_name="search_policy",
                arguments={},
                result={"policy": "14 days"},
                success=True,
            )],
        ),
        execution_trace=ExecutionTrace(
            trace_id=trace_id,
            run_id="run",
            spans=[root, tool, synthesis],
        ),
    )
