from evaluation.context import EvaluationContext
from evaluation.models import EvaluationEvidence, EvaluationLevel, GradeResult, Verdict
from tracing.models import TraceNodeType, TraceStatus


class TraceStructureGrader:
    name = "trace_structure"
    version = "1.0.0"

    def evaluate(self, context: EvaluationContext) -> list[GradeResult]:
        trace = context.execution_trace
        roots = [
            span for span in trace.spans
            if span.node_type == TraceNodeType.AGENT_EXECUTION and span.parent_span_id is None
        ]
        evidence = [EvaluationEvidence(
            assertion="agent_root_count",
            expected=1,
            observed=len(roots),
            span_id=roots[0].span_id if roots else None,
        )]
        violations: list[tuple[object, str, object, object]] = []
        root_id = roots[0].span_id if len(roots) == 1 else None

        for span in trace.spans:
            if span.trace_id != trace.trace_id:
                violations.append((span, "span_trace_id", trace.trace_id, span.trace_id))
            if span.status == TraceStatus.RUNNING:
                violations.append((span, "span_completed", True, False))
            if span.ended_at is None:
                violations.append((span, "span_ended_at", "datetime", None))
            if span.latency_ms is None or span.latency_ms < 0:
                violations.append((span, "non_negative_latency", True, span.latency_ms))
            if span.node_type in {TraceNodeType.TOOL_EXECUTION, TraceNodeType.SYNTHESIS} and (
                root_id is None
                or not self._is_descendant(span.parent_span_id, root_id, trace.spans)
            ):
                violations.append((span, "descendant_of_agent_root", True, False))

        for span, assertion, expected, observed in violations:
            evidence.append(EvaluationEvidence(
                assertion=assertion,
                expected=expected,
                observed=observed,
                span_id=span.span_id,
            ))
        passed = len(roots) == 1 and not violations
        target = violations[0][0].span_id if violations else (roots[0].span_id if roots else None)
        return [GradeResult(
            grader_name=self.name,
            grader_version=self.version,
            level=EvaluationLevel.RUN,
            verdict=Verdict.PASS if passed else Verdict.FAIL,
            score=1.0 if passed else 0.0,
            target_span_id=target,
            summary=f"Trace structure is {'valid' if passed else 'invalid'}.",
            evidence=evidence,
        )]

    @staticmethod
    def _is_descendant(parent_id: object, root_id: object, spans: list[object]) -> bool:
        parents = {span.span_id: span.parent_span_id for span in spans}
        current = parent_id
        visited: set[object] = set()
        while current is not None and current not in visited:
            if current == root_id:
                return True
            visited.add(current)
            current = parents.get(current)
        return False
