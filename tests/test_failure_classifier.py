from copy import deepcopy

import pytest

from dag.builder import EvaluationDAGBuilder
from dag.models import RootCauseAttribution, RootCauseReport
from dag.propagation import RootCauseAnalyzer
from evaluation.models import (
    EvaluationEvidence,
    EvaluationLevel,
    EvaluationReport,
    GradeResult,
    Verdict,
)
from evaluation.taxonomy.catalog import FailureTaxonomyCatalog
from evaluation.taxonomy.classifier import FailureTaxonomyClassifier
from evaluation.taxonomy.models import ClassificationConfidence
from faults.models import FaultActivationRecord, FaultType
from tracing.models import TraceNodeType


def failed_grade(assertion, span_id, grader_name="test"):
    return GradeResult(
        grader_name=grader_name,
        grader_version="1",
        level=EvaluationLevel.STEP,
        verdict=Verdict.FAIL,
        target_span_id=span_id,
        summary="failed",
        evidence=[EvaluationEvidence(assertion=assertion, expected=True, observed=False)],
    )


def report_for(context, verdict, grades):
    return EvaluationReport(
        run_id=context.execution_trace.run_id,
        scenario_id=context.scenario.id,
        scenario_version=1,
        overall_verdict=verdict,
        grades=grades,
    )


def classifier():
    return FailureTaxonomyClassifier(FailureTaxonomyCatalog.load())


@pytest.mark.parametrize(
    ("fault_type", "expected_path"),
    [
        (FaultType.TOOL_TIMEOUT, ("EXECUTION", "API_TOOL_FAILURE", "TIMEOUT")),
        (FaultType.TOOL_ERROR, ("EXECUTION", "API_TOOL_FAILURE", "ERROR_RESPONSE")),
        (FaultType.MALFORMED_OUTPUT, ("EXECUTION", "API_TOOL_FAILURE", "MALFORMED_RESULT")),
        (FaultType.BAD_RETRIEVAL, ("RETRIEVAL", "RESULT_QUALITY", "INCORRECT_RESULT")),
        (FaultType.CONTEXT_TRUNCATION, ("INTEGRATION", "CONTEXT_LOSS", "TRUNCATION")),
    ],
)
def test_fault_mappings(evaluation_context, fault_type, expected_path) -> None:
    tool = evaluation_context.execution_trace.spans_by_type(TraceNodeType.TOOL_EXECUTION)[0]
    synthesis = evaluation_context.execution_trace.spans_by_type(TraceNodeType.SYNTHESIS)[0]
    fault = FaultActivationRecord(
        fault_id="fault",
        fault_type=fault_type,
        target_tool=tool.name,
        call_number=1,
        activated=True,
        reason="test",
    )
    evaluation = report_for(
        evaluation_context,
        Verdict.FAIL,
        [failed_grade("unknown_assertion", synthesis.span_id)],
    )
    dag = EvaluationDAGBuilder().build(
        evaluation_context.execution_trace, evaluation, [fault]
    )
    roots = RootCauseAnalyzer().analyze(dag, evaluation)
    result = classifier().classify(dag, evaluation, roots, [fault])
    classification = result.classifications[0]
    assert classification.taxonomy_path.identifiers == expected_path
    assert classification.confidence == ClassificationConfidence.HIGH
    assert classification.confidence_score == 1.0
    assert classification.fault_id == "fault"


@pytest.mark.parametrize(
    ("assertion", "expected_path"),
    [
        ("required_tool_called", ("PLANNING", "MISSING_STEP", "TOOL_OMISSION")),
        (
            "required_claim_present",
            ("INTEGRATION", "OUTPUT_QUALITY", "REQUIRED_CLAIM_MISSING"),
        ),
        (
            "forbidden_claim_present",
            ("INTEGRATION", "OUTPUT_QUALITY", "FORBIDDEN_CLAIM_PRESENT"),
        ),
    ],
)
def test_grade_mappings(evaluation_context, assertion, expected_path) -> None:
    target = evaluation_context.execution_trace.spans[0]
    evaluation = report_for(
        evaluation_context, Verdict.FAIL, [failed_grade(assertion, target.span_id)]
    )
    dag = EvaluationDAGBuilder().build(evaluation_context.execution_trace, evaluation)
    roots = RootCauseAnalyzer().analyze(dag, evaluation)
    result = classifier().classify(dag, evaluation, roots)
    assert result.classifications[0].taxonomy_path.identifiers == expected_path
    assert result.classifications[0].confidence_score == 0.8


def test_insufficient_evidence_maps_to_unknown(evaluation_context) -> None:
    target = evaluation_context.execution_trace.spans[1]
    evaluation = report_for(
        evaluation_context,
        Verdict.FAIL,
        [failed_grade("not_mapped", target.span_id)],
    )
    dag = EvaluationDAGBuilder().build(evaluation_context.execution_trace, evaluation)
    roots = RootCauseAnalyzer().analyze(dag, evaluation)
    result = classifier().classify(dag, evaluation, roots)
    assert result.classifications[0].taxonomy_path.identifiers == (
        "UNKNOWN", "UNCLASSIFIED", "INSUFFICIENT_EVIDENCE"
    )
    assert result.classifications[0].confidence_score == 0.2


def test_equal_candidates_preserve_ambiguity(evaluation_context) -> None:
    root = evaluation_context.execution_trace.spans[0]
    grade = failed_grade("required_tool_called", root.span_id)
    evaluation = report_for(evaluation_context, Verdict.FAIL, [grade])
    dag = EvaluationDAGBuilder().build(evaluation_context.execution_trace, evaluation)
    attribution = RootCauseAttribution(
        root_node_id=root.span_id,
        affected_node_ids=[root.span_id],
        confidence=0.5,
        reason="multiple equally near candidates exist",
    )
    roots = RootCauseReport(
        run_id=dag.run_id,
        scenario_id=evaluation.scenario_id,
        overall_verdict=Verdict.FAIL,
        attributions=[attribution],
        summary="ambiguous",
    )
    result = classifier().classify(dag, evaluation, roots)
    classification = result.classifications[0]
    assert classification.taxonomy_path.identifiers == (
        "UNKNOWN", "AMBIGUOUS", "MULTIPLE_PLAUSIBLE_CAUSES"
    )
    assert classification.alternative_paths[0].level3 == "TOOL_OMISSION"
    assert root.span_id in result.ambiguous_root_nodes


def test_propagated_node_is_affected_not_separately_classified(evaluation_context) -> None:
    root, _, synthesis = evaluation_context.execution_trace.spans
    grades = [
        failed_grade("required_tool_called", root.span_id),
        failed_grade("required_claim_present", synthesis.span_id),
    ]
    evaluation = report_for(evaluation_context, Verdict.FAIL, grades)
    dag = EvaluationDAGBuilder().build(evaluation_context.execution_trace, evaluation)
    roots = RootCauseAnalyzer().analyze(dag, evaluation)
    result = classifier().classify(dag, evaluation, roots)
    assert len(result.classifications) == 1
    assert synthesis.span_id in result.classifications[0].affected_node_ids


def test_classifier_does_not_mutate_inputs(evaluation_context) -> None:
    target = evaluation_context.execution_trace.spans[0]
    evaluation = report_for(
        evaluation_context,
        Verdict.FAIL,
        [failed_grade("required_tool_called", target.span_id)],
    )
    dag = EvaluationDAGBuilder().build(evaluation_context.execution_trace, evaluation)
    roots = RootCauseAnalyzer().analyze(dag, evaluation)
    before = (deepcopy(dag), deepcopy(evaluation), deepcopy(roots))
    classifier().classify(dag, evaluation, roots)
    assert (dag, evaluation, roots) == before
