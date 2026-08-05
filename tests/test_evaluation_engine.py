from types import SimpleNamespace

import pytest

from evaluation.aggregation import aggregate_verdict
from evaluation.engine import DeterministicEvaluationEngine
from evaluation.models import EvaluationLevel, GradeResult, Verdict


def grade(verdict: Verdict, name: str = "test") -> GradeResult:
    return GradeResult(
        grader_name=name,
        grader_version="1",
        level=EvaluationLevel.RUN,
        verdict=verdict,
        summary=name,
    )


@pytest.mark.parametrize(
    ("verdicts", "expected"),
    [
        ([Verdict.PASS], Verdict.PASS),
        ([Verdict.PASS, Verdict.FAIL], Verdict.FAIL),
        ([Verdict.PASS, Verdict.INCONCLUSIVE], Verdict.INCONCLUSIVE),
        ([Verdict.FAIL, Verdict.ERROR], Verdict.ERROR),
    ],
)
def test_aggregation(verdicts: list[Verdict], expected: Verdict) -> None:
    assert aggregate_verdict([grade(verdict) for verdict in verdicts]) == expected


def test_engine_preserves_order_and_runs_after_failure(evaluation_context) -> None:
    calls: list[str] = []

    class Grader:
        version = "1"

        def __init__(self, name: str, verdict: Verdict) -> None:
            self.name = name
            self.verdict = verdict

        def evaluate(self, context):
            calls.append(self.name)
            return [grade(self.verdict, self.name)]

    report = DeterministicEvaluationEngine([
        Grader("first", Verdict.FAIL),
        Grader("second", Verdict.PASS),
    ]).evaluate(evaluation_context)

    assert calls == ["first", "second"]
    assert [item.grader_name for item in report.grades] == ["first", "second"]
    assert report.overall_verdict == Verdict.FAIL


def test_grader_exception_becomes_error(evaluation_context) -> None:
    broken = SimpleNamespace(
        name="broken",
        version="2",
        evaluate=lambda context: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    report = DeterministicEvaluationEngine([broken]).evaluate(evaluation_context)
    assert report.overall_verdict == Verdict.ERROR
    assert report.grades[0].verdict == Verdict.ERROR
    assert "RuntimeError: boom" in report.grades[0].summary
