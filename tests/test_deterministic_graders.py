from datetime import UTC, datetime

from evaluation.deterministic import (
    ClaimGrader,
    FaultRecoveryGrader,
    ToolOutcomeGrader,
    ToolUsageGrader,
    TraceStructureGrader,
)
from evaluation.models import Verdict
from scenarios.models import ResponseExpectation, ResponseMode, ToolOutcomeExpectation
from tracing.models import TraceNodeType, TraceSpan, TraceStatus


def test_required_tool_present_and_missing(evaluation_context) -> None:
    grader = ToolUsageGrader()
    assert grader.evaluate(evaluation_context)[0].verdict == Verdict.PASS
    evaluation_context.scenario.expected.required_tools = ["missing"]
    result = grader.evaluate(evaluation_context)[0]
    assert result.verdict == Verdict.FAIL
    assert result.evidence[0].expected is True
    assert result.evidence[0].observed is False


def test_expected_tool_outcomes_and_error_substring(evaluation_context) -> None:
    expectation = ToolOutcomeExpectation(tool_name="search_policy", expected_success=True)
    evaluation_context.scenario.expected.tool_outcomes = [expectation]
    assert ToolOutcomeGrader().evaluate(evaluation_context)[0].verdict == Verdict.PASS

    call = evaluation_context.agent_result.tool_calls[0]
    call.success = False
    call.error = "Injected TIMEOUT from service"
    evaluation_context.scenario.expected.tool_outcomes = [ToolOutcomeExpectation(
        tool_name="search_policy",
        expected_success=False,
        expected_error_contains="timeout",
    )]
    result = ToolOutcomeGrader().evaluate(evaluation_context)[0]
    assert result.verdict == Verdict.PASS
    assert evaluation_context.execution_trace.spans[1].status == TraceStatus.SUCCESS

    evaluation_context.scenario.expected.tool_outcomes[0].expected_error_contains = "other"
    assert ToolOutcomeGrader().evaluate(evaluation_context)[0].verdict == Verdict.FAIL


def test_required_and_forbidden_claims(evaluation_context) -> None:
    expected = evaluation_context.scenario.expected
    expected.required_claims = ["14   DAYS", "missing claim"]
    expected.forbidden_claims = ["30 days", "14 days"]
    verdicts = [grade.verdict for grade in ClaimGrader().evaluate(evaluation_context)]
    assert verdicts == [Verdict.PASS, Verdict.FAIL, Verdict.PASS, Verdict.FAIL]


def test_response_markers_pass_and_fail(evaluation_context) -> None:
    evaluation_context.agent_result.answer = "Policy data was invalid or unusable."
    evaluation_context.scenario.expected.response = ResponseExpectation(
        mode=ResponseMode.INVALID_DATA,
        required_markers=["invalid", "unusable"],
    )
    assert FaultRecoveryGrader().evaluate(evaluation_context)[0].verdict == Verdict.PASS
    evaluation_context.scenario.expected.response.required_markers.append("missing")
    assert FaultRecoveryGrader().evaluate(evaluation_context)[0].verdict == Verdict.FAIL


def test_valid_trace_and_invalid_root_count(evaluation_context) -> None:
    grader = TraceStructureGrader()
    assert grader.evaluate(evaluation_context)[0].verdict == Verdict.PASS
    root = evaluation_context.execution_trace.spans[0].model_copy(deep=True)
    root.span_id = TraceSpan(
        trace_id=root.trace_id,
        node_type=TraceNodeType.AGENT_EXECUTION,
        name="second",
        started_at=datetime.now(UTC),
    ).span_id
    evaluation_context.execution_trace.spans.append(root)
    assert grader.evaluate(evaluation_context)[0].verdict == Verdict.FAIL


def test_running_span_fails_trace_structure(evaluation_context) -> None:
    span = evaluation_context.execution_trace.spans[1]
    span.status = TraceStatus.RUNNING
    span.ended_at = None
    span.latency_ms = None
    result = TraceStructureGrader().evaluate(evaluation_context)[0]
    assert result.verdict == Verdict.FAIL
    assert result.target_span_id == span.span_id
