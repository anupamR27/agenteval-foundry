from copy import deepcopy

from dag.builder import EvaluationDAGBuilder
from evaluation.models import EvaluationLevel, EvaluationReport, GradeResult, Verdict
from faults.models import FaultActivationRecord, FaultType
from tracing.models import TraceNodeType


def make_report(context, grades):
    return EvaluationReport(
        run_id=context.execution_trace.run_id,
        scenario_id=context.scenario.id,
        scenario_version=context.scenario.version,
        overall_verdict=Verdict.PASS,
        grades=grades,
    )


def make_grade(name, target_span_id=None):
    return GradeResult(
        grader_name=name,
        grader_version="1",
        level=EvaluationLevel.STEP,
        verdict=Verdict.PASS,
        target_span_id=target_span_id,
        summary=name,
    )


def test_builder_reconstructs_stable_nodes_and_edges(evaluation_context) -> None:
    trace = evaluation_context.execution_trace
    dag = EvaluationDAGBuilder().build(trace, make_report(evaluation_context, []))
    assert [node.node_id for node in dag.nodes] == [span.span_id for span in trace.spans]
    assert len(dag.nodes) == len(trace.spans) == 3
    assert dag.root_node_ids == [trace.spans[0].span_id]
    assert [(edge.source_node_id, edge.target_node_id) for edge in dag.edges] == [
        (trace.spans[0].span_id, trace.spans[1].span_id),
        (trace.spans[0].span_id, trace.spans[2].span_id),
    ]
    assert dag.children(trace.spans[0].span_id) == [dag.nodes[1], dag.nodes[2]]
    assert dag.parents(trace.spans[1].span_id) == [dag.nodes[0]]


def test_builder_attaches_grades_faults_and_unscoped_grades(evaluation_context) -> None:
    tool_span = evaluation_context.execution_trace.spans_by_type(TraceNodeType.TOOL_EXECUTION)[0]
    scoped = make_grade("scoped", tool_span.span_id)
    unscoped = make_grade("unscoped")
    fault = FaultActivationRecord(
        fault_id="fault-1",
        fault_type=FaultType.TOOL_TIMEOUT,
        target_tool="search_policy",
        call_number=1,
        activated=True,
        reason="test",
    )
    dag = EvaluationDAGBuilder().build(
        evaluation_context.execution_trace,
        make_report(evaluation_context, [scoped, unscoped]),
        [fault],
    )
    tool_node = dag.node(tool_span.span_id)
    assert [grade.grader_name for grade in tool_node.attached_grades] == ["scoped"]
    assert [item.fault_id for item in tool_node.attached_faults] == ["fault-1"]
    assert [grade.grader_name for grade in dag.unscoped_grades] == ["unscoped"]


def test_builder_does_not_mutate_inputs(evaluation_context) -> None:
    grade = make_grade("scoped", evaluation_context.execution_trace.spans[1].span_id)
    report = make_report(evaluation_context, [grade])
    trace_before = deepcopy(evaluation_context.execution_trace)
    report_before = deepcopy(report)
    dag = EvaluationDAGBuilder().build(evaluation_context.execution_trace, report)
    dag.nodes[1].attached_grades[0].summary = "changed"
    assert evaluation_context.execution_trace == trace_before
    assert report == report_before
