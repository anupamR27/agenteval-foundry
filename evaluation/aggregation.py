from collections.abc import Sequence

from evaluation.models import GradeResult, Verdict


def aggregate_verdict(grades: Sequence[GradeResult]) -> Verdict:
    verdicts = {grade.verdict for grade in grades}
    if Verdict.ERROR in verdicts:
        return Verdict.ERROR
    if Verdict.FAIL in verdicts:
        return Verdict.FAIL
    if Verdict.INCONCLUSIVE in verdicts:
        return Verdict.INCONCLUSIVE
    return Verdict.PASS
