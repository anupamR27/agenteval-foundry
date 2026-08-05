import pytest

from dag.models import DagNodeStatus
from dag.propagation import RootCauseAnalyzer
from evaluation.models import EvaluationEvidence, EvaluationLevel, GradeResult, Verdict
from evaluation.taxonomy.catalog import FailureTaxonomyCatalog
from evaluation.taxonomy.classifier import FailureTaxonomyClassifier
from evaluation.taxonomy.models import ClassificationConfidence
from faults.models import FaultType
from tests.test_dag_integration import analyze_scenario
from tracing.models import TraceNodeType


def classify(dag, evaluation, roots):
    return FailureTaxonomyClassifier(FailureTaxonomyCatalog.load()).classify(
        dag, evaluation, roots
    )


@pytest.mark.asyncio
async def test_normal_has_no_failure_classification() -> None:
    evaluation, dag, roots = await analyze_scenario("normal.yaml")
    report = classify(dag, evaluation, roots)
    assert evaluation.overall_verdict == Verdict.PASS
    assert report.classifications == []


@pytest.mark.asyncio
async def test_timeout_remains_handled_without_classification() -> None:
    evaluation, dag, roots = await analyze_scenario("tool_timeout.yaml")
    tool = next(node for node in dag.nodes if node.node_type == TraceNodeType.TOOL_EXECUTION)
    report = classify(dag, evaluation, roots)
    assert evaluation.overall_verdict == Verdict.PASS
    assert tool.evaluation_status == DagNodeStatus.DISTURBANCE_HANDLED
    assert report.classifications == []


@pytest.mark.asyncio
async def test_bad_retrieval_classifies_root_and_affected_synthesis() -> None:
    evaluation, dag, roots = await analyze_scenario("bad_retrieval.yaml")
    tool = next(node for node in dag.nodes if node.node_type == TraceNodeType.TOOL_EXECUTION)
    synthesis = next(node for node in dag.nodes if node.node_type == TraceNodeType.SYNTHESIS)
    report = classify(dag, evaluation, roots)
    assert len(report.classifications) == 1
    classification = report.classifications[0]
    assert classification.root_node_id == tool.node_id
    assert classification.taxonomy_path.identifiers == (
        "RETRIEVAL", "RESULT_QUALITY", "INCORRECT_RESULT"
    )
    assert classification.confidence == ClassificationConfidence.HIGH
    assert classification.fault_id == tool.attached_faults[0].fault_id
    assert synthesis.node_id in classification.affected_node_ids


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["malformed_output.yaml", "context_truncation.yaml"])
async def test_handled_data_disturbances_have_no_classification(filename: str) -> None:
    evaluation, dag, roots = await analyze_scenario(filename)
    assert evaluation.overall_verdict == Verdict.PASS
    assert classify(dag, evaluation, roots).classifications == []


@pytest.mark.asyncio
async def test_failed_truncation_recovery_classifies_context_loss() -> None:
    evaluation, dag, _ = await analyze_scenario("context_truncation.yaml")
    synthesis = next(node for node in dag.nodes if node.node_type == TraceNodeType.SYNTHESIS)
    recovery_failure = GradeResult(
        grader_name="fault_recovery",
        grader_version="1.0.0",
        level=EvaluationLevel.RUN,
        verdict=Verdict.FAIL,
        target_span_id=synthesis.node_id,
        summary="Recovery marker was missing.",
        evidence=[EvaluationEvidence(
            assertion="required_response_marker_present",
            expected=True,
            observed=False,
            span_id=synthesis.node_id,
        )],
    )
    synthesis.attached_grades.append(recovery_failure)
    evaluation.overall_verdict = Verdict.FAIL
    evaluation.grades.append(recovery_failure)
    roots = RootCauseAnalyzer().analyze(dag, evaluation)
    report = classify(dag, evaluation, roots)
    classification = report.classifications[0]
    assert classification.taxonomy_path.identifiers == (
        "INTEGRATION", "CONTEXT_LOSS", "TRUNCATION"
    )
    assert classification.confidence_score == 1.0
    assert dag.node(classification.root_node_id).attached_faults[0].fault_type == (
        FaultType.CONTEXT_TRUNCATION
    )
