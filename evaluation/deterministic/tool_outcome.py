from evaluation.context import EvaluationContext
from evaluation.models import EvaluationEvidence, EvaluationLevel, GradeResult, Verdict
from tracing.models import TraceNodeType


class ToolOutcomeGrader:
    name = "tool_outcome"
    version = "1.0.0"

    def evaluate(self, context: EvaluationContext) -> list[GradeResult]:
        grades: list[GradeResult] = []
        tool_spans = context.execution_trace.spans_by_type(TraceNodeType.TOOL_EXECUTION)
        for expectation in context.scenario.expected.tool_outcomes:
            calls = [
                call for call in context.agent_result.tool_calls
                if call.tool_name == expectation.tool_name
            ]
            spans = [span for span in tool_spans if span.name == expectation.tool_name]
            evidence: list[EvaluationEvidence] = []
            checks: list[bool] = []

            if expectation.expected_call_count is not None:
                call_count_ok = len(calls) == expectation.expected_call_count
                checks.append(call_count_ok)
                evidence.append(EvaluationEvidence(
                    assertion="tool_call_count",
                    expected=expectation.expected_call_count,
                    observed=len(calls),
                    span_id=spans[0].span_id if spans else None,
                ))

            success_values = [call.success for call in calls]
            success_ok = bool(calls) and all(
                value is expectation.expected_success for value in success_values
            )
            checks.append(success_ok)
            evidence.append(EvaluationEvidence(
                assertion="tool_success",
                expected=expectation.expected_success,
                observed=success_values,
                span_id=spans[0].span_id if spans else None,
            ))

            if expectation.expected_error_contains is not None:
                expected_error = expectation.expected_error_contains.casefold()
                observed_errors = [call.error for call in calls]
                error_ok = bool(calls) and all(
                    call.error is not None and expected_error in call.error.casefold()
                    for call in calls
                )
                checks.append(error_ok)
                evidence.append(EvaluationEvidence(
                    assertion="tool_error_contains",
                    expected=expectation.expected_error_contains,
                    observed=observed_errors,
                    span_id=spans[0].span_id if spans else None,
                ))

            passed = all(checks)
            grades.append(GradeResult(
                grader_name=self.name,
                grader_version=self.version,
                level=EvaluationLevel.STEP,
                verdict=Verdict.PASS if passed else Verdict.FAIL,
                score=1.0 if passed else 0.0,
                target_span_id=spans[0].span_id if spans else None,
                summary=f"Tool outcome for {expectation.tool_name!r} "
                f"{'matched' if passed else 'did not match'} expectations.",
                evidence=evidence,
                metadata={"tool_name": expectation.tool_name},
            ))
        return grades
