from collections import deque
from uuid import UUID

from dag.models import (
    DagNodeStatus,
    EvaluationDAG,
    EvaluationDagNode,
    RootCauseAttribution,
    RootCauseReport,
)
from dag.validation import validate_dag
from evaluation.models import EvaluationEvidence, EvaluationReport, Verdict


class RootCauseAnalyzer:
    """Produce conservative, heuristic root-cause attributions."""

    def analyze(self, dag: EvaluationDAG, report: EvaluationReport) -> RootCauseReport:
        validate_dag(dag)
        for node in dag.nodes:
            node.evaluation_status = DagNodeStatus.HEALTHY

        failing_unscoped = [
            grade for grade in dag.unscoped_grades
            if grade.verdict in {Verdict.FAIL, Verdict.ERROR}
        ]
        if report.overall_verdict == Verdict.PASS:
            handled = []
            for node in dag.nodes:
                if node.attached_faults or node.execution_status == "ERROR":
                    node.evaluation_status = DagNodeStatus.DISTURBANCE_HANDLED
                    handled.append(node.node_id)
            return RootCauseReport(
                run_id=dag.run_id,
                scenario_id=report.scenario_id,
                overall_verdict=report.overall_verdict,
                handled_disturbance_nodes=handled,
                unattributed_grades=failing_unscoped,
                summary="No evaluation failure occurred; observed disturbances were handled.",
            )

        failed_nodes = [node for node in dag.nodes if self._has_failed_grade(node)]
        attributions: dict[UUID, RootCauseAttribution] = {}
        for failed_node in sorted(failed_nodes, key=self._topological_key):
            candidates = self._nearest_candidates(dag, failed_node)
            if not candidates:
                failed_node.evaluation_status = DagNodeStatus.FAILED_LOCAL
                self._add_attribution(attributions, failed_node, failed_node, 0.8)
                continue
            failed_node.evaluation_status = DagNodeStatus.FAILED_PROPAGATED
            confidence = 1.0 if any(node.attached_faults for node in candidates) else 0.6
            if len(candidates) > 1:
                confidence = min(confidence, 0.5)
            for candidate in candidates:
                candidate.evaluation_status = DagNodeStatus.FAILED_LOCAL
                self._add_attribution(
                    attributions,
                    candidate,
                    failed_node,
                    confidence,
                    ambiguous=len(candidates) > 1,
                )

        unattributed_nodes = [
            node.node_id for node in failed_nodes
            if node.evaluation_status == DagNodeStatus.UNKNOWN
        ]
        summary = (
            f"Heuristic analysis identified {len(attributions)} root-cause candidate(s) "
            f"for {len(failed_nodes)} failed node(s)."
        )
        return RootCauseReport(
            run_id=dag.run_id,
            scenario_id=report.scenario_id,
            overall_verdict=report.overall_verdict,
            attributions=list(attributions.values()),
            unattributed_failed_nodes=unattributed_nodes,
            unattributed_grades=failing_unscoped,
            summary=summary,
        )

    @staticmethod
    def _has_failed_grade(node: EvaluationDagNode) -> bool:
        return any(grade.verdict in {Verdict.FAIL, Verdict.ERROR} for grade in node.attached_grades)

    @staticmethod
    def _topological_key(node: EvaluationDagNode) -> int:
        return node.topological_index if node.topological_index is not None else 0

    def _nearest_candidates(
        self,
        dag: EvaluationDAG,
        failed_node: EvaluationDagNode,
    ) -> list[EvaluationDagNode]:
        queue = deque((parent_id, 1) for parent_id in failed_node.parent_ids)
        seen: set[UUID] = set()
        candidates: list[EvaluationDagNode] = []
        candidate_distance: int | None = None
        while queue:
            node_id, distance = queue.popleft()
            if node_id in seen or (candidate_distance is not None and distance > candidate_distance):
                continue
            seen.add(node_id)
            node = dag.node(node_id)
            if node.attached_faults or self._has_failed_grade(node):
                candidate_distance = distance
                candidates.append(node)
                continue
            queue.extend((parent_id, distance + 1) for parent_id in node.parent_ids)
        if candidates:
            return candidates

        failed_index = self._topological_key(failed_node)
        earlier_faults = [
            node for node in dag.nodes
            if node.attached_faults and self._topological_key(node) < failed_index
        ]
        if not earlier_faults:
            return []
        nearest_index = max(self._topological_key(node) for node in earlier_faults)
        return [node for node in earlier_faults if self._topological_key(node) == nearest_index]

    def _add_attribution(
        self,
        attributions: dict[UUID, RootCauseAttribution],
        root: EvaluationDagNode,
        affected: EvaluationDagNode,
        confidence: float,
        ambiguous: bool = False,
    ) -> None:
        failed_grades = [
            grade for grade in affected.attached_grades
            if grade.verdict in {Verdict.FAIL, Verdict.ERROR}
        ]
        fault = root.attached_faults[0] if root.attached_faults else None
        evidence = [item for grade in failed_grades for item in grade.evidence]
        if fault is not None:
            evidence.insert(0, EvaluationEvidence(
                assertion="activated_fault",
                expected="no harmful downstream effect",
                observed=fault.fault_type,
                span_id=root.node_id,
                metadata={"fault_id": fault.fault_id},
            ))
        reason = "Heuristic attribution to "
        if fault and root.node_id not in affected.parent_ids:
            reason += "an earlier injected fault in the validated trace"
        elif fault:
            reason += "an injected fault upstream"
        else:
            reason += "the nearest failed deterministic step"
        if ambiguous:
            reason += "; multiple equally near candidates exist"
        existing = attributions.get(root.node_id)
        if existing is None:
            attributions[root.node_id] = RootCauseAttribution(
                root_node_id=root.node_id,
                affected_node_ids=[affected.node_id],
                confidence=confidence,
                reason=reason,
                evidence=evidence,
                fault_id=fault.fault_id if fault else None,
                originating_grade_names=list(dict.fromkeys(
                    grade.grader_name for grade in failed_grades
                )),
            )
        else:
            if affected.node_id not in existing.affected_node_ids:
                existing.affected_node_ids.append(affected.node_id)
            existing.confidence = min(existing.confidence, confidence)
            existing.evidence.extend(evidence)
            names = existing.originating_grade_names or []
            existing.originating_grade_names = list(dict.fromkeys(
                [*names, *(grade.grader_name for grade in failed_grades)]
            ))
