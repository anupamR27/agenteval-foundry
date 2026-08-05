from pathlib import Path
from uuid import uuid4

import pytest

from aut.base import AgentRequest, ExecutionContext
from aut.stub_agent import StubAgent
from dag.builder import EvaluationDAGBuilder
from dag.models import DagNodeStatus
from dag.propagation import RootCauseAnalyzer
from dag.validation import validate_dag
from evaluation.context import EvaluationContext
from evaluation.engine import DeterministicEvaluationEngine
from evaluation.models import Verdict
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

SCENARIO_DIR = Path("scenarios/examples")


async def analyze_scenario(filename: str):
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
    evaluation = DeterministicEvaluationEngine.default().evaluate(EvaluationContext(
        scenario=scenario,
        agent_result=result,
        execution_trace=collector.trace,
        fault_activation_records=fault_executor.activation_records,
    ))
    dag = validate_dag(EvaluationDAGBuilder().build(
        collector.trace,
        evaluation,
        fault_executor.activation_records,
    ))
    root_causes = RootCauseAnalyzer().analyze(dag, evaluation)
    return evaluation, dag, root_causes


@pytest.mark.asyncio
async def test_normal_dag_is_healthy() -> None:
    evaluation, dag, root_causes = await analyze_scenario("normal.yaml")
    assert evaluation.overall_verdict == Verdict.PASS
    assert len(dag.nodes) == 3
    assert all(node.evaluation_status == DagNodeStatus.HEALTHY for node in dag.nodes)
    assert root_causes.attributions == []


@pytest.mark.asyncio
async def test_timeout_dag_marks_handled_disturbance() -> None:
    evaluation, dag, root_causes = await analyze_scenario("tool_timeout.yaml")
    tool = next(node for node in dag.nodes if node.node_type == TraceNodeType.TOOL_EXECUTION)
    assert tool.execution_status == TraceStatus.ERROR
    assert tool.evaluation_status == DagNodeStatus.DISTURBANCE_HANDLED
    assert evaluation.overall_verdict == Verdict.PASS
    assert root_causes.attributions == []


@pytest.mark.asyncio
async def test_bad_retrieval_propagates_from_fault_node() -> None:
    evaluation, dag, root_causes = await analyze_scenario("bad_retrieval.yaml")
    tool = next(node for node in dag.nodes if node.node_type == TraceNodeType.TOOL_EXECUTION)
    synthesis = next(node for node in dag.nodes if node.node_type == TraceNodeType.SYNTHESIS)
    assert evaluation.overall_verdict == Verdict.FAIL
    assert tool.execution_status == TraceStatus.SUCCESS
    assert tool.evaluation_status == DagNodeStatus.FAILED_LOCAL
    assert synthesis.evaluation_status == DagNodeStatus.FAILED_PROPAGATED
    attribution = root_causes.attributions[0]
    assert attribution.root_node_id == tool.node_id
    assert attribution.fault_id is not None
    assert attribution.confidence == 1.0
    assert tool.attached_faults[0].fault_type == FaultType.BAD_RETRIEVAL


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["malformed_output.yaml", "context_truncation.yaml"])
async def test_recovered_data_faults_are_handled(filename: str) -> None:
    evaluation, dag, root_causes = await analyze_scenario(filename)
    fault_nodes = [node for node in dag.nodes if node.attached_faults]
    assert evaluation.overall_verdict == Verdict.PASS
    assert fault_nodes
    assert all(
        node.evaluation_status == DagNodeStatus.DISTURBANCE_HANDLED
        for node in fault_nodes
    )
    assert root_causes.attributions == []
