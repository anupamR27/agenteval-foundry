from typing import Protocol

from evaluation.context import EvaluationContext
from evaluation.models import GradeResult


class DeterministicGrader(Protocol):
    name: str
    version: str

    def evaluate(self, context: EvaluationContext) -> list[GradeResult]:
        ...
