import argparse
import asyncio
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

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
from persistence.repository import PersistenceError, RunRepository
from scenarios.loader import load_scenario
from tools.mock_tools import build_default_tool_registry
from tracing.collector import TraceCollector
from tracing.instrumentation import (
    TraceSynthesisRecorder,
    TracingAgentExecutor,
    TracingToolExecutor,
)

DEFAULT_SCENARIO_PATH = Path("scenarios/examples/normal.yaml")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one AgentEval Foundry scenario.")
    parser.add_argument(
        "--scenario",
        type=Path,
        default=DEFAULT_SCENARIO_PATH,
        help=f"Scenario YAML path. Defaults to {DEFAULT_SCENARIO_PATH}.",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist the completed run to PostgreSQL.",
    )
    return parser.parse_args()


async def _persist_bundle(bundle: RunBundle) -> None:
    from persistence.postgres.config import PostgresConfig
    from persistence.postgres.repository import PostgresRunRepository

    implementation = PostgresRunRepository.from_config(PostgresConfig.from_env())
    repository: RunRepository = implementation
    try:
        await repository.save(bundle)
    finally:
        await implementation.close()


async def run(scenario_path: Path = DEFAULT_SCENARIO_PATH, *, persist: bool = False) -> None:
    try:
        scenario = load_scenario(scenario_path)
    except FileNotFoundError as exc:
        print(f"File error: {exc}")
        raise SystemExit(1) from exc
    except (TypeError, ValueError, ValidationError) as exc:
        print(f"Scenario validation failed:\n{exc}")
        raise SystemExit(1) from exc

    run_id = str(uuid4())
    collector = TraceCollector(run_id=run_id)
    registry = build_default_tool_registry()
    fault_executor = FaultInjectingToolExecutor(registry, scenario.fault_profile)
    tool_executor = TracingToolExecutor(fault_executor, collector)
    agent = StubAgent(
        tool_registry=tool_executor,
        synthesis_recorder=TraceSynthesisRecorder(collector),
    )
    traced_agent = TracingAgentExecutor(agent, collector)
    result = await traced_agent.execute(
        AgentRequest(query=scenario.query, scenario_id=scenario.id),
        ExecutionContext(run_id=run_id, scenario_version=scenario.version),
    )
    evaluation = DeterministicEvaluationEngine.default().evaluate(
        EvaluationContext(
            scenario=scenario,
            agent_result=result,
            execution_trace=collector.trace,
            fault_activation_records=fault_executor.activation_records,
        )
    )
    evaluation_dag = validate_dag(EvaluationDAGBuilder().build(
        collector.trace,
        evaluation,
        fault_executor.activation_records,
    ))
    root_cause_report = RootCauseAnalyzer().analyze(evaluation_dag, evaluation)
    classification_report = FailureTaxonomyClassifier(FailureTaxonomyCatalog.load()).classify(
        evaluation_dag,
        evaluation,
        root_cause_report,
        fault_executor.activation_records,
    )
    bundle = RunBundle.from_pipeline(
        scenario=scenario,
        agent_result=result,
        execution_trace=collector.trace,
        fault_activation_records=fault_executor.activation_records,
        evaluation_report=evaluation,
        evaluation_dag=evaluation_dag,
        root_cause_report=root_cause_report,
        failure_classification_report=classification_report,
    )

    print("AgentEval Foundry")
    print("=================")
    print(f"Run ID: {run_id}")
    print(f"Scenario ID: {scenario.id}")
    print(f"Version: {scenario.version}")
    print(f"Name: {scenario.name}")
    print(f"Query: {scenario.query}")
    print(f"Required tools: {scenario.expected.required_tools}")
    print(f"Required claims: {scenario.expected.required_claims}")
    print(f"Forbidden claims: {scenario.expected.forbidden_claims}")
    print(f"Fault profile: {scenario.fault_profile}")
    print()
    print(f"Agent: {result.agent_metadata.name} v{result.agent_metadata.version}")
    print(f"Final answer: {result.answer}")
    print("Observed tool calls:")
    for tool_call in result.tool_calls:
        status = "succeeded" if tool_call.success else "failed"
        print(f"- {tool_call.tool_name}: {status}")
        print(f"  Arguments: {tool_call.arguments}")
        print(f"  Result: {tool_call.result}")
        if tool_call.error:
            print(f"  Error: {tool_call.error}")
    print()
    print("Activated faults:")
    if not fault_executor.activation_records:
        print("none")
    for record in fault_executor.activation_records:
        print(
            f"- {record.fault_type}: {record.target_tool} "
            f"call={record.call_number} fault_id={record.fault_id}"
        )
        print(f"  Reason: {record.reason}")
    print()
    print(f"Trace ID: {collector.trace.trace_id}")
    print("Trace summary:")
    for span in collector.trace.spans:
        parent = str(span.parent_span_id) if span.parent_span_id is not None else "ROOT"
        latency = f"{span.latency_ms:.3f}" if span.latency_ms is not None else "n/a"
        print(
            f"- {span.node_type}: {span.name} | "
            f"status={span.status} | parent={parent} | latency_ms={latency}"
        )
    print()
    print("Evaluation summary:")
    print(f"Overall verdict: {evaluation.overall_verdict}")
    print(
        f"Passed: {evaluation.passed_count} | Failed: {evaluation.failed_count} | "
        f"Inconclusive: {evaluation.inconclusive_count} | Errors: {evaluation.error_count}"
    )
    print("Grades:")
    for grade in evaluation.grades:
        target = f" | span={grade.target_span_id}" if grade.target_span_id else ""
        print(f"- {grade.grader_name}: {grade.verdict} | {grade.summary}{target}")
        for evidence in grade.evidence:
            evidence_span = f" | span={evidence.span_id}" if evidence.span_id else ""
            print(
                f"  {evidence.assertion}: expected={evidence.expected!r} "
                f"observed={evidence.observed!r}{evidence_span}"
            )
    print()
    print("Evaluation DAG:")
    for node in evaluation_dag.nodes:
        parents = ", ".join(str(item) for item in node.parent_ids) or "ROOT"
        faults = ", ".join(str(item.fault_type) for item in node.attached_faults) or "none"
        print(
            f"- {node.node_type}: {node.name} | status={node.evaluation_status} | "
            f"parents={parents} | grades={len(node.attached_grades)} | faults={faults}"
        )
    print()
    print("Root-cause analysis:")
    print(root_cause_report.summary)
    for attribution in root_cause_report.attributions:
        affected = ", ".join(str(item) for item in attribution.affected_node_ids)
        print(
            f"- root={attribution.root_node_id} | confidence={attribution.confidence:.2f} | "
            f"affected={affected}"
        )
        print(f"  Reason: {attribution.reason}")
        if attribution.fault_id:
            print(f"  Fault ID: {attribution.fault_id}")
        for evidence in attribution.evidence:
            print(
                f"  Evidence {evidence.assertion}: expected={evidence.expected!r} "
                f"observed={evidence.observed!r}"
            )
    if root_cause_report.unattributed_failed_nodes:
        print(f"Unattributed failed nodes: {root_cause_report.unattributed_failed_nodes}")
    if root_cause_report.unattributed_grades:
        names = [grade.grader_name for grade in root_cause_report.unattributed_grades]
        print(f"Unattributed failed grades: {names}")
    print()
    print("Failure taxonomy:")
    print(f"Taxonomy version: {classification_report.taxonomy_version}")
    if not classification_report.classifications:
        print("No evaluation failure required classification.")
    for classification in classification_report.classifications:
        path = classification.taxonomy_path
        affected = ", ".join(str(item) for item in classification.affected_node_ids) or "none"
        print(f"- {path.level1} / {path.level2} / {path.level3}")
        print(
            f"  Root: {classification.root_node_id} | confidence={classification.confidence} "
            f"({classification.confidence_score:.2f})"
        )
        print(f"  Reason: {classification.reason}")
        if classification.fault_id:
            print(f"  Fault ID: {classification.fault_id}")
        print(f"  Affected nodes: {affected}")
        if classification.alternative_paths:
            alternatives = [
                " / ".join(alternative.identifiers)
                for alternative in classification.alternative_paths
            ]
            print(f"  Alternative paths: {alternatives}")
    if persist:
        try:
            await _persist_bundle(bundle)
        except PersistenceError as exc:
            concise_error = str(exc).splitlines()[0]
            print(f"Persistence failed: {concise_error}")
            raise SystemExit(1) from exc
        print(f"Persisted run: {run_id}")


def main() -> None:
    args = parse_args()
    asyncio.run(run(args.scenario, persist=args.persist))


if __name__ == "__main__":
    main()
