from pathlib import Path

import pytest

from aut.base import AgentRequest, ExecutionContext
from aut.stub_agent import StubAgent
from faults.injector import FaultInjectingToolExecutor
from faults.models import FaultType
from scenarios.loader import load_scenario
from tools.mock_tools import build_default_tool_registry
from tracing.collector import TraceCollector
from tracing.instrumentation import (
    TraceSynthesisRecorder,
    TracingAgentExecutor,
    TracingToolExecutor,
)
from tracing.models import TraceNodeType, TraceStatus


async def run_scenario(path: str) -> tuple:
    scenario = load_scenario(Path(path))
    collector = TraceCollector(run_id="test-run")
    fault_executor = FaultInjectingToolExecutor(
        build_default_tool_registry(),
        scenario.fault_profile,
    )
    agent = StubAgent(
        TracingToolExecutor(fault_executor, collector),
        synthesis_recorder=TraceSynthesisRecorder(collector),
    )
    result = await TracingAgentExecutor(agent, collector).execute(
        AgentRequest(query=scenario.query, scenario_id=scenario.id),
        ExecutionContext(run_id="test-run", scenario_version=scenario.version),
    )
    return result, collector, fault_executor


@pytest.mark.asyncio
async def test_normal_scenario_has_no_faults_and_successful_trace() -> None:
    result, collector, fault_executor = await run_scenario("scenarios/examples/normal.yaml")

    assert "14 days" in result.answer
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].success is True
    assert len(collector.trace.spans) == 3
    assert {span.status for span in collector.trace.spans} == {TraceStatus.SUCCESS}
    assert fault_executor.activation_records == ()


@pytest.mark.asyncio
async def test_timeout_scenario_records_failed_tool_and_error_span() -> None:
    result, collector, fault_executor = await run_scenario("scenarios/examples/tool_timeout.yaml")

    assert len(fault_executor.activation_records) == 1
    assert fault_executor.activation_records[0].fault_type == FaultType.TOOL_TIMEOUT
    assert result.tool_calls[0].success is False
    assert result.answer == "The refund policy could not be retrieved."
    tool_span = collector.trace.spans_by_type(TraceNodeType.TOOL_EXECUTION)[0]
    assert tool_span.status == TraceStatus.ERROR


@pytest.mark.asyncio
async def test_tool_error_scenario_returns_safe_answer() -> None:
    result, _, fault_executor = await run_scenario("scenarios/examples/tool_error.yaml")

    assert len(fault_executor.activation_records) == 1
    assert fault_executor.activation_records[0].fault_type == FaultType.TOOL_ERROR
    assert result.answer == "The refund policy could not be retrieved."


@pytest.mark.asyncio
async def test_malformed_output_scenario_returns_invalid_data_answer() -> None:
    result, collector, _ = await run_scenario("scenarios/examples/malformed_output.yaml")

    assert result.answer == "The returned policy data was invalid or unusable."
    assert result.tool_calls[0].result == {"unexpected_field": 123}
    tool_span = collector.trace.spans_by_type(TraceNodeType.TOOL_EXECUTION)[0]
    assert tool_span.output_data["data"] == {"unexpected_field": 123}


@pytest.mark.asyncio
async def test_bad_retrieval_scenario_succeeds_with_incorrect_content() -> None:
    result, collector, fault_executor = await run_scenario("scenarios/examples/bad_retrieval.yaml")

    assert result.tool_calls[0].success is True
    assert "30 days" in result.answer
    assert fault_executor.activation_records[0].fault_type == FaultType.BAD_RETRIEVAL
    tool_span = collector.trace.spans_by_type(TraceNodeType.TOOL_EXECUTION)[0]
    assert tool_span.status == TraceStatus.SUCCESS


@pytest.mark.asyncio
async def test_context_truncation_scenario_returns_incomplete_answer() -> None:
    result, _, fault_executor = await run_scenario("scenarios/examples/context_truncation.yaml")

    assert result.tool_calls[0].success is True
    assert result.answer == "The available policy information is incomplete or insufficient."
    assert fault_executor.activation_records[0].fault_type == FaultType.CONTEXT_TRUNCATION
