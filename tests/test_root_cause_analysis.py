from dag.builder import EvaluationDAGBuilder
from dag.models import DagNodeStatus
from dag.propagation import RootCauseAnalyzer
from evaluation.models import EvaluationEvidence, EvaluationLevel, GradeResult, Verdict
from faults.models import FaultActivationRecord, FaultType
from tracing.models import TraceNodeType, TraceStatus


def failed_grade(name, span_id=None):
    return GradeResult(
        grader_name=name,
        grader_version="1",
        level=EvaluationLevel.STEP,
        verdict=Verdict.FAIL,
        target_span_id=span_id,
        summary="failed",
        evidence=[EvaluationEvidence(assertion="check", expected=True, observed=False)],
    )


def report_for(context, verdict, grades):
    from evaluation.models import EvaluationReport

    return EvaluationReport(
        run_id=context.execution_trace.run_id,
        scenario_id=context.scenario.id,
        scenario_version=1,
        overall_verdict=verdict,
        grades=grades,
    )


def test_pass_has_no_attribution_and_execution_error_is_handled(evaluation_context) -> None:
    tool = evaluation_context.execution_trace.spans[1]
    tool.status = TraceStatus.ERROR
    report = report_for(evaluation_context, Verdict.PASS, [])
    dag = EvaluationDAGBuilder().build(evaluation_context.execution_trace, report)
    result = RootCauseAnalyzer().analyze(dag, report)
    assert result.attributions == []
    assert dag.node(tool.span_id).evaluation_status == DagNodeStatus.DISTURBANCE_HANDLED


def test_direct_failure_is_local_with_deterministic_confidence(evaluation_context) -> None:
    tool = evaluation_context.execution_trace.spans[1]
    report = report_for(evaluation_context, Verdict.FAIL, [failed_grade("tool", tool.span_id)])
    dag = EvaluationDAGBuilder().build(evaluation_context.execution_trace, report)
    result = RootCauseAnalyzer().analyze(dag, report)
    assert dag.node(tool.span_id).evaluation_status == DagNodeStatus.FAILED_LOCAL
    assert result.attributions[0].root_node_id == tool.span_id
    assert result.attributions[0].confidence == 0.8


def test_failed_descendant_propagates_from_failed_ancestor(evaluation_context) -> None:
    root, _, synthesis = evaluation_context.execution_trace.spans
    grades = [failed_grade("root", root.span_id), failed_grade("child", synthesis.span_id)]
    report = report_for(evaluation_context, Verdict.FAIL, grades)
    dag = EvaluationDAGBuilder().build(evaluation_context.execution_trace, report)
    result = RootCauseAnalyzer().analyze(dag, report)
    assert dag.node(root.span_id).evaluation_status == DagNodeStatus.FAILED_LOCAL
    assert dag.node(synthesis.span_id).evaluation_status == DagNodeStatus.FAILED_PROPAGATED
    attribution = next(item for item in result.attributions if item.root_node_id == root.span_id)
    assert synthesis.span_id in attribution.affected_node_ids
    assert attribution.confidence == 0.6


def test_bad_retrieval_fault_is_upstream_cause(evaluation_context) -> None:
    tool = evaluation_context.execution_trace.spans_by_type(TraceNodeType.TOOL_EXECUTION)[0]
    synthesis = evaluation_context.execution_trace.spans_by_type(TraceNodeType.SYNTHESIS)[0]
    fault = FaultActivationRecord(
        fault_id="bad",
        fault_type=FaultType.BAD_RETRIEVAL,
        target_tool=tool.name,
        call_number=1,
        activated=True,
        reason="test",
    )
    report = report_for(evaluation_context, Verdict.FAIL, [failed_grade("claims", synthesis.span_id)])
    dag = EvaluationDAGBuilder().build(evaluation_context.execution_trace, report, [fault])
    result = RootCauseAnalyzer().analyze(dag, report)
    assert dag.node(tool.span_id).evaluation_status == DagNodeStatus.FAILED_LOCAL
    assert dag.node(synthesis.span_id).evaluation_status == DagNodeStatus.FAILED_PROPAGATED
    assert result.attributions[0].fault_id == "bad"
    assert result.attributions[0].confidence == 1.0


def test_unscoped_failure_remains_visible(evaluation_context) -> None:
    report = report_for(evaluation_context, Verdict.FAIL, [failed_grade("unscoped")])
    dag = EvaluationDAGBuilder().build(evaluation_context.execution_trace, report)
    result = RootCauseAnalyzer().analyze(dag, report)
    assert [grade.grader_name for grade in result.unattributed_grades] == ["unscoped"]


def test_equal_nearest_candidates_are_preserved(evaluation_context) -> None:
    root, tool, synthesis = evaluation_context.execution_trace.spans
    synthesis.parent_span_id = tool.span_id
    extra = tool.model_copy(deep=True)
    extra.span_id = root.model_copy().span_id
    from uuid import uuid4

    extra.span_id = uuid4()
    extra.parent_span_id = root.span_id
    evaluation_context.execution_trace.spans.append(extra)
    # Give synthesis two explicit parents through the built DAG to model a join.
    report = report_for(evaluation_context, Verdict.FAIL, [failed_grade("claims", synthesis.span_id)])
    dag = EvaluationDAGBuilder().build(evaluation_context.execution_trace, report)
    dag.node(synthesis.span_id).parent_ids = [tool.span_id, extra.span_id]
    dag.node(extra.span_id).child_ids.append(synthesis.span_id)
    from dag.models import EvaluationDagEdge

    dag.edges.append(EvaluationDagEdge(
        source_node_id=extra.span_id,
        target_node_id=synthesis.span_id,
    ))
    dag.node(tool.span_id).attached_grades.append(failed_grade("left", tool.span_id))
    dag.node(extra.span_id).attached_grades.append(failed_grade("right", extra.span_id))
    result = RootCauseAnalyzer().analyze(dag, report)
    roots = {item.root_node_id for item in result.attributions}
    assert {tool.span_id, extra.span_id}.issubset(roots)
    assert all(item.confidence <= 0.5 for item in result.attributions)
