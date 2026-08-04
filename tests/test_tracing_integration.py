import pytest

from aut.base import AgentRequest, ExecutionContext
from aut.stub_agent import StubAgent
from tools.base import ToolDefinition, ToolResult
from tools.mock_tools import build_default_tool_registry
from tools.registry import ToolRegistry
from tracing.collector import TraceCollector
from tracing.instrumentation import (
    TraceSynthesisRecorder,
    TracingAgentExecutor,
    TracingToolExecutor,
)
from tracing.models import TraceNodeType, TraceStatus


@pytest.mark.asyncio
async def test_traced_stub_agent_records_agent_tool_and_synthesis_spans() -> None:
    collector = TraceCollector(run_id="test-run")
    agent = StubAgent(
        TracingToolExecutor(build_default_tool_registry(), collector),
        synthesis_recorder=TraceSynthesisRecorder(collector),
    )
    traced_agent = TracingAgentExecutor(agent, collector)

    result = await traced_agent.execute(
        AgentRequest(
            query="Find the refund period for an annual subscription.",
            scenario_id="demo-normal-001",
        ),
        ExecutionContext(run_id="test-run", scenario_version=1),
    )

    assert "14 days" in result.answer
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "search_policy"
    assert result.tool_calls[0].success is True

    agent_spans = collector.trace.spans_by_type(TraceNodeType.AGENT_EXECUTION)
    tool_spans = collector.trace.spans_by_type(TraceNodeType.TOOL_EXECUTION)
    synthesis_spans = collector.trace.spans_by_type(TraceNodeType.SYNTHESIS)

    assert len(agent_spans) == 1
    assert len(tool_spans) == 1
    assert len(synthesis_spans) == 1
    assert tool_spans[0].parent_span_id == agent_spans[0].span_id
    assert synthesis_spans[0].parent_span_id == agent_spans[0].span_id
    assert tool_spans[0].name == "search_policy"
    assert {span.status for span in collector.trace.spans} == {TraceStatus.SUCCESS}


async def failing_search_policy(query: str) -> ToolResult:
    return ToolResult(success=False, data=None, error=f"policy unavailable for: {query}")


@pytest.mark.asyncio
async def test_failed_tool_result_is_reflected_in_trace_and_agent_result() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="search_policy",
            description="Failing policy lookup.",
            handler=failing_search_policy,
        )
    )
    collector = TraceCollector(run_id="test-run")
    agent = StubAgent(
        TracingToolExecutor(registry, collector),
        synthesis_recorder=TraceSynthesisRecorder(collector),
    )
    traced_agent = TracingAgentExecutor(agent, collector)

    result = await traced_agent.execute(
        AgentRequest(query="Find the refund period.", scenario_id="demo-normal-001"),
        ExecutionContext(run_id="test-run", scenario_version=1),
    )

    assert result.answer == "The refund policy could not be retrieved."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "search_policy"
    assert result.tool_calls[0].success is False

    tool_span = collector.trace.spans_by_type(TraceNodeType.TOOL_EXECUTION)[0]
    synthesis_span = collector.trace.spans_by_type(TraceNodeType.SYNTHESIS)[0]
    assert tool_span.status == TraceStatus.ERROR
    assert tool_span.error == "policy unavailable for: Find the refund period."
    assert synthesis_span.status == TraceStatus.SUCCESS
