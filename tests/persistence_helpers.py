from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from aut.base import AgentRequest, ExecutionContext
from aut.stub_agent import StubAgent
from dag.builder import EvaluationDAGBuilder
from dag.propagation import RootCauseAnalyzer
from dag.validation import validate_dag
from evaluation.context import EvaluationContext
from evaluation.engine import DeterministicEvaluationEngine
from evaluation.taxonomy.catalog import FailureTaxonomyCatalog
from evaluation.taxonomy.classifier import FailureTaxonomyClassifier
from faults.injector import FaultInjectingToolExecutor
from persistence.models import RunBundle
from persistence.serialization import bundle_from_dict, bundle_to_dict
from scenarios.loader import load_scenario
from tools.mock_tools import build_default_tool_registry
from tracing.collector import TraceCollector
from tracing.instrumentation import (
    TraceSynthesisRecorder,
    TracingAgentExecutor,
    TracingToolExecutor,
)


def build_bundle(context: EvaluationContext) -> RunBundle:
    evaluation = DeterministicEvaluationEngine.default().evaluate(context)
    dag = validate_dag(EvaluationDAGBuilder().build(
        context.execution_trace,
        evaluation,
        context.fault_activation_records,
    ))
    roots = RootCauseAnalyzer().analyze(dag, evaluation)
    classifications = FailureTaxonomyClassifier(FailureTaxonomyCatalog.load()).classify(
        dag,
        evaluation,
        roots,
        context.fault_activation_records,
    )
    return RunBundle.from_pipeline(
        scenario=context.scenario,
        agent_result=context.agent_result,
        execution_trace=context.execution_trace,
        fault_activation_records=context.fault_activation_records,
        evaluation_report=evaluation,
        evaluation_dag=dag,
        root_cause_report=roots,
        failure_classification_report=classifications,
        created_at=datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
    )


def replace_run_id(bundle: RunBundle, run_id: UUID) -> RunBundle:
    data = bundle_to_dict(bundle)
    value = str(run_id)
    data["run_id"] = value
    data["execution_trace"]["run_id"] = value
    data["evaluation_report"]["run_id"] = value
    data["evaluation_dag"]["run_id"] = value
    data["root_cause_report"]["run_id"] = value
    data["failure_classification_report"]["run_id"] = value
    return bundle_from_dict(data)


async def execute_bundle(filename: str) -> RunBundle:
    scenario = load_scenario(Path("scenarios/examples") / filename)
    run_id = str(UUID(int=42))
    collector = TraceCollector(run_id)
    fault_executor = FaultInjectingToolExecutor(
        build_default_tool_registry(), scenario.fault_profile
    )
    agent = StubAgent(
        TracingToolExecutor(fault_executor, collector),
        TraceSynthesisRecorder(collector),
    )
    result = await TracingAgentExecutor(agent, collector).execute(
        AgentRequest(query=scenario.query, scenario_id=scenario.id),
        ExecutionContext(run_id=run_id, scenario_version=scenario.version),
    )
    context = EvaluationContext(
        scenario=scenario,
        agent_result=result,
        execution_trace=collector.trace,
        fault_activation_records=fault_executor.activation_records,
    )
    return build_bundle(context)
