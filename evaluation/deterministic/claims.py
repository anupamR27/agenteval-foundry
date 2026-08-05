import re

from evaluation.context import EvaluationContext
from evaluation.models import EvaluationEvidence, EvaluationLevel, GradeResult, Verdict
from tracing.models import TraceNodeType


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


class ClaimGrader:
    name = "claims"
    version = "1.0.0"

    def evaluate(self, context: EvaluationContext) -> list[GradeResult]:
        answer = normalize_text(context.agent_result.answer)
        synthesis = next(iter(context.execution_trace.spans_by_type(TraceNodeType.SYNTHESIS)), None)
        span_id = synthesis.span_id if synthesis else None
        grades: list[GradeResult] = []
        for claim in context.scenario.expected.required_claims:
            present = normalize_text(claim) in answer
            grades.append(self._grade(claim, True, present, span_id))
        for claim in context.scenario.expected.forbidden_claims:
            present = normalize_text(claim) in answer
            grades.append(self._grade(claim, False, present, span_id))
        return grades

    def _grade(self, claim: str, expected_present: bool, observed_present: bool, span_id: object) -> GradeResult:
        passed = observed_present is expected_present
        expectation = "required" if expected_present else "forbidden"
        return GradeResult(
            grader_name=self.name,
            grader_version=self.version,
            level=EvaluationLevel.RUN,
            verdict=Verdict.PASS if passed else Verdict.FAIL,
            score=1.0 if passed else 0.0,
            target_span_id=span_id,
            summary=f"{expectation.title()} claim {claim!r} was "
            f"{'handled correctly' if passed else 'violated'}.",
            evidence=[EvaluationEvidence(
                assertion=f"{expectation}_claim_present",
                expected=expected_present,
                observed=observed_present,
                span_id=span_id,
                metadata={"claim": claim},
            )],
        )
