from evaluation.context import EvaluationContext
from evaluation.deterministic.claims import normalize_text
from evaluation.models import EvaluationEvidence, EvaluationLevel, GradeResult, Verdict
from tracing.models import TraceNodeType


class FaultRecoveryGrader:
    name = "fault_recovery"
    version = "1.0.0"

    def evaluate(self, context: EvaluationContext) -> list[GradeResult]:
        expectation = context.scenario.expected.response
        if expectation is None:
            return []

        answer = normalize_text(context.agent_result.answer)
        synthesis = next(iter(context.execution_trace.spans_by_type(TraceNodeType.SYNTHESIS)), None)
        span_id = synthesis.span_id if synthesis else None
        evidence: list[EvaluationEvidence] = []
        checks: list[bool] = []
        for marker in expectation.required_markers:
            present = normalize_text(marker) in answer
            checks.append(present)
            evidence.append(EvaluationEvidence(
                assertion="required_response_marker_present",
                expected=True,
                observed=present,
                span_id=span_id,
                metadata={"marker": marker},
            ))
        for marker in expectation.forbidden_markers:
            present = normalize_text(marker) in answer
            checks.append(not present)
            evidence.append(EvaluationEvidence(
                assertion="forbidden_response_marker_present",
                expected=False,
                observed=present,
                span_id=span_id,
                metadata={"marker": marker},
            ))

        if not checks:
            return [GradeResult(
                grader_name=self.name,
                grader_version=self.version,
                level=EvaluationLevel.RUN,
                verdict=Verdict.INCONCLUSIVE,
                target_span_id=span_id,
                summary=f"Response mode {expectation.mode} has no deterministic markers.",
                evidence=[EvaluationEvidence(
                    assertion="response_markers_configured",
                    expected=True,
                    observed=False,
                    span_id=span_id,
                )],
            )]

        passed = all(checks)
        return [GradeResult(
            grader_name=self.name,
            grader_version=self.version,
            level=EvaluationLevel.RUN,
            verdict=Verdict.PASS if passed else Verdict.FAIL,
            score=1.0 if passed else 0.0,
            target_span_id=span_id,
            summary=f"Response {'matched' if passed else 'did not match'} "
            f"{expectation.mode} expectations.",
            evidence=evidence,
        )]
