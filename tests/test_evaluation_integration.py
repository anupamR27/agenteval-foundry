from pathlib import Path
from uuid import uuid4

import pytest

from aut.base import AgentRequest, ExecutionContext
from aut.stub_agent import StubAgent
from evaluation.context import EvaluationContext
from evaluation.engine import DeterministicEvaluationEngine
from evaluation.models import Verdict
from faults.injector import FaultInjectingToolExecutor
from scenarios.loader import load_scenario
from tools.mock_tools import build_default_tool_registry
from tracing.collector import TraceCollector
from tracing.instrumentation import (
    TraceSynthesisRecorder,
    TracingAgentExecutor,
    TracingToolExecutor,
)
from tracing.models import TraceNodeType, TraceStatus

SCENARIO_DIR = Path("scenarios/examples")


async def evaluate_scenario(filename: str):
    scenario = load_scenario(SCENARIO_DIR / filename)
    run_id = str(uuid4())
    collector = TraceCollector(run_id)
    fault_executor = FaultInjectingToolExecutor(
        build_default_tool_registry(),
        scenario.fault_profile,
    )
    agent = StubAgent(
        TracingToolExecutor(fault_executor, collector),
        TraceSynthesisRecorder(collector),
    )
    result = await TracingAgentExecutor(agent, collector).execute(
        AgentRequest(query=scenario.query, scenario_id=scenario.id),
        ExecutionContext(run_id=run_id, scenario_version=scenario.version),
    )
    report = DeterministicEvaluationEngine.default().evaluate(EvaluationContext(
        scenario=scenario,
        agent_result=result,
        execution_trace=collector.trace,
        fault_activation_records=fault_executor.activation_records,
    ))
    return report, collector.trace


@pytest.mark.asyncio
async def test_normal_scenario_passes() -> None:
    report, _ = await evaluate_scenario("normal.yaml")
    assert report.overall_verdict == Verdict.PASS
    assert all(
        grade.verdict == Verdict.PASS
        for grade in report.grades
        if grade.grader_name in {"tool_usage", "claims"}
    )


@pytest.mark.asyncio
async def test_timeout_failure_is_expected_and_recovered() -> None:
    report, trace = await evaluate_scenario("tool_timeout.yaml")
    tool_span = trace.spans_by_type(TraceNodeType.TOOL_EXECUTION)[0]
    assert tool_span.status == TraceStatus.ERROR
    assert report.overall_verdict == Verdict.PASS
    assert next(
        grade for grade in report.grades if grade.grader_name == "tool_outcome"
    ).verdict == Verdict.PASS
    assert next(
        grade for grade in report.grades if grade.grader_name == "fault_recovery"
    ).verdict == Verdict.PASS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filename",
    ["tool_error.yaml", "malformed_output.yaml", "context_truncation.yaml"],
)
async def test_recoverable_fault_scenarios_pass(filename: str) -> None:
    report, _ = await evaluate_scenario(filename)
    assert report.overall_verdict == Verdict.PASS


@pytest.mark.asyncio
async def test_bad_retrieval_fails_claims_not_execution() -> None:
    report, trace = await evaluate_scenario("bad_retrieval.yaml")
    assert report.overall_verdict == Verdict.FAIL
    assert all(span.status == TraceStatus.SUCCESS for span in trace.spans)
    assert next(
        grade for grade in report.grades if grade.grader_name == "tool_outcome"
    ).verdict == Verdict.PASS
    claim_grades = [grade for grade in report.grades if grade.grader_name == "claims"]
    assert [grade.verdict for grade in claim_grades] == [Verdict.FAIL, Verdict.FAIL]
