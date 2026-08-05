from evaluation.context import EvaluationContext
from evaluation.models import EvaluationEvidence, EvaluationLevel, GradeResult, Verdict
from tracing.models import TraceNodeType


class ToolUsageGrader:
    name = "tool_usage"
    version = "1.0.0"

    def evaluate(self, context: EvaluationContext) -> list[GradeResult]:
        grades: list[GradeResult] = []
        tool_spans = context.execution_trace.spans_by_type(TraceNodeType.TOOL_EXECUTION)
        for tool_name in context.scenario.expected.required_tools:
            calls = [call for call in context.agent_result.tool_calls if call.tool_name == tool_name]
            span = next((item for item in tool_spans if item.name == tool_name), None)
            passed = bool(calls)
            grades.append(
                GradeResult(
                    grader_name=self.name,
                    grader_version=self.version,
                    level=EvaluationLevel.STEP,
                    verdict=Verdict.PASS if passed else Verdict.FAIL,
                    score=1.0 if passed else 0.0,
                    target_span_id=span.span_id if span else None,
                    summary=f"Required tool {tool_name!r} was {'called' if passed else 'not called'}.",
                    evidence=[EvaluationEvidence(
                        assertion="required_tool_called",
                        expected=True,
                        observed=passed,
                        span_id=span.span_id if span else None,
                        metadata={"tool_name": tool_name, "call_count": len(calls)},
                    )],
                )
            )
        return grades
