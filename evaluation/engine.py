from collections.abc import Iterable

from evaluation.aggregation import aggregate_verdict
from evaluation.context import EvaluationContext
from evaluation.deterministic import (
    ClaimGrader,
    FaultRecoveryGrader,
    ToolOutcomeGrader,
    ToolUsageGrader,
    TraceStructureGrader,
)
from evaluation.deterministic.base import DeterministicGrader
from evaluation.models import EvaluationLevel, EvaluationReport, GradeResult, Verdict


class DeterministicEvaluationEngine:
    def __init__(self, graders: Iterable[DeterministicGrader]) -> None:
        self._graders = tuple(graders)

    @classmethod
    def default(cls) -> "DeterministicEvaluationEngine":
        return cls([
            ToolUsageGrader(),
            ToolOutcomeGrader(),
            ClaimGrader(),
            FaultRecoveryGrader(),
            TraceStructureGrader(),
        ])

    def evaluate(self, context: EvaluationContext) -> EvaluationReport:
        grades: list[GradeResult] = []
        for grader in self._graders:
            try:
                grades.extend(grader.evaluate(context))
            except Exception as exc:  # noqa: BLE001 - grader isolation is required here.
                grades.append(GradeResult(
                    grader_name=grader.name,
                    grader_version=grader.version,
                    level=EvaluationLevel.RUN,
                    verdict=Verdict.ERROR,
                    summary=f"Grader raised {type(exc).__name__}: {exc}",
                    metadata={"exception_type": type(exc).__name__},
                ))

        counts = {verdict: sum(grade.verdict == verdict for grade in grades) for verdict in Verdict}
        overall = aggregate_verdict(grades)
        return EvaluationReport(
            run_id=context.execution_trace.run_id,
            scenario_id=context.scenario.id,
            scenario_version=context.scenario.version,
            overall_verdict=overall,
            grades=grades,
            passed_count=counts[Verdict.PASS],
            failed_count=counts[Verdict.FAIL],
            inconclusive_count=counts[Verdict.INCONCLUSIVE],
            error_count=counts[Verdict.ERROR],
            summary=f"Evaluation completed with overall verdict {overall}.",
        )
