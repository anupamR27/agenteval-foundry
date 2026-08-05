from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from uuid import NAMESPACE_URL, UUID, uuid5

from dag.models import EvaluationDAG, RootCauseAttribution, RootCauseReport
from evaluation.models import EvaluationEvidence, EvaluationReport, GradeResult, Verdict
from evaluation.taxonomy.catalog import FailureTaxonomyCatalog
from evaluation.taxonomy.models import (
    ClassificationConfidence,
    ClassificationSource,
    FailureClassification,
    FailureClassificationReport,
    FailureTaxonomyPath,
)
from faults.models import FaultActivationRecord, FaultType

PathKey = tuple[str, str, str]

DEFAULT_FAULT_PATHS: Mapping[FaultType, PathKey] = MappingProxyType({
    FaultType.TOOL_TIMEOUT: ("EXECUTION", "API_TOOL_FAILURE", "TIMEOUT"),
    FaultType.TOOL_ERROR: ("EXECUTION", "API_TOOL_FAILURE", "ERROR_RESPONSE"),
    FaultType.MALFORMED_OUTPUT: ("EXECUTION", "API_TOOL_FAILURE", "MALFORMED_RESULT"),
    FaultType.BAD_RETRIEVAL: ("RETRIEVAL", "RESULT_QUALITY", "INCORRECT_RESULT"),
    FaultType.CONTEXT_TRUNCATION: ("INTEGRATION", "CONTEXT_LOSS", "TRUNCATION"),
})

DEFAULT_GRADE_PATHS: Mapping[str, PathKey] = MappingProxyType({
    "required_tool_called": ("PLANNING", "MISSING_STEP", "TOOL_OMISSION"),
    "required_claim_present": (
        "INTEGRATION", "OUTPUT_QUALITY", "REQUIRED_CLAIM_MISSING"
    ),
    "forbidden_claim_present": (
        "INTEGRATION", "OUTPUT_QUALITY", "FORBIDDEN_CLAIM_PRESENT"
    ),
    "descendant_of_agent_root": (
        "ORCHESTRATION", "WORKFLOW_STRUCTURE", "DEPENDENCY_VIOLATION"
    ),
    "agent_root_count": ("ORCHESTRATION", "WORKFLOW_STRUCTURE", "MULTIPLE_ROOTS"),
    "all_nodes_reachable": ("ORCHESTRATION", "WORKFLOW_STRUCTURE", "UNREACHABLE_NODE"),
})


@dataclass(frozen=True)
class ClassificationSignal:
    path: PathKey
    confidence: ClassificationConfidence
    score: float
    source: ClassificationSource
    reason: str
    evidence: tuple[EvaluationEvidence, ...]
    fault_id: str | None = None


class FailureTaxonomyClassifier:
    """Classify heuristic root causes from deterministic, observable evidence."""

    def __init__(
        self,
        catalog: FailureTaxonomyCatalog,
        fault_paths: Mapping[FaultType, PathKey] | None = None,
        grade_paths: Mapping[str, PathKey] | None = None,
    ) -> None:
        self._catalog = catalog
        self._fault_paths = dict(fault_paths or DEFAULT_FAULT_PATHS)
        self._grade_paths = dict(grade_paths or DEFAULT_GRADE_PATHS)

    def classify(
        self,
        dag: EvaluationDAG,
        evaluation_report: EvaluationReport,
        root_cause_report: RootCauseReport,
        fault_activation_records: Sequence[FaultActivationRecord] = (),
    ) -> FailureClassificationReport:
        if evaluation_report.overall_verdict == Verdict.PASS:
            return FailureClassificationReport(
                run_id=dag.run_id,
                scenario_id=evaluation_report.scenario_id,
                taxonomy_version=self._catalog.version,
                summary="No evaluation failure required classification.",
            )

        active_faults = {
            fault.fault_id: fault for fault in fault_activation_records if fault.activated
        }
        classifications: list[FailureClassification] = []
        unclassified: list[UUID] = []
        ambiguous: list[UUID] = []
        for attribution in root_cause_report.attributions:
            try:
                node = dag.node(attribution.root_node_id)
            except KeyError:
                unclassified.append(attribution.root_node_id)
                continue

            signal = self._fault_signal(node.attached_faults, attribution, active_faults)
            grade_signals = self._grade_signals(node.attached_grades)
            direct_fault_signal = signal
            if signal is None and grade_signals:
                signal = grade_signals[0]

            is_ambiguous = "multiple equally" in attribution.reason.casefold()
            alternatives: list[FailureTaxonomyPath] = []
            if is_ambiguous:
                ambiguous.append(node.node_id)
                candidate_signals = ([signal] if signal else []) + grade_signals
                alternatives = self._unique_paths(candidate_signals)
                signal = ClassificationSignal(
                    path=("UNKNOWN", "AMBIGUOUS", "MULTIPLE_PLAUSIBLE_CAUSES"),
                    confidence=ClassificationConfidence.LOW,
                    score=0.3,
                    source=ClassificationSource.HEURISTIC,
                    reason="Multiple equally plausible heuristic root causes remain.",
                    evidence=tuple(attribution.evidence),
                )
            else:
                if signal is None:
                    signal = ClassificationSignal(
                        path=("UNKNOWN", "UNCLASSIFIED", "INSUFFICIENT_EVIDENCE"),
                        confidence=ClassificationConfidence.LOW,
                        score=0.2,
                        source=ClassificationSource.UNKNOWN,
                        reason="Structured evidence is insufficient for a specific classification.",
                        evidence=tuple(attribution.evidence),
                    )
                competing = grade_signals if direct_fault_signal else grade_signals[1:]
                alternatives = [
                    path for path in self._unique_paths(competing)
                    if path.identifiers != signal.path
                ]
                if alternatives:
                    ambiguous.append(node.node_id)

            classifications.append(FailureClassification(
                classification_id=uuid5(
                    NAMESPACE_URL,
                    f"agenteval:{dag.run_id}:{evaluation_report.scenario_id}:"
                    f"{node.node_id}:{'/'.join(signal.path)}",
                ),
                root_node_id=node.node_id,
                taxonomy_path=self._catalog.resolve(*signal.path),
                confidence=signal.confidence,
                confidence_score=signal.score,
                reason=signal.reason,
                evidence=[item.model_copy(deep=True) for item in signal.evidence],
                source=signal.source,
                fault_id=signal.fault_id or attribution.fault_id,
                affected_node_ids=list(attribution.affected_node_ids),
                alternative_paths=alternatives,
                metadata={"attribution_confidence": attribution.confidence},
            ))

        return FailureClassificationReport(
            run_id=dag.run_id,
            scenario_id=evaluation_report.scenario_id,
            taxonomy_version=self._catalog.version,
            classifications=classifications,
            unclassified_root_nodes=unclassified,
            ambiguous_root_nodes=ambiguous,
            summary=f"Classified {len(classifications)} heuristic root-cause candidate(s).",
        )

    def _fault_signal(
        self,
        attached_faults: Sequence[FaultActivationRecord],
        attribution: RootCauseAttribution,
        active_faults: dict[str, FaultActivationRecord],
    ) -> ClassificationSignal | None:
        faults = list(attached_faults)
        if attribution.fault_id in active_faults and not any(
            fault.fault_id == attribution.fault_id for fault in faults
        ):
            faults.append(active_faults[attribution.fault_id])
        mapped = [
            fault for fault in faults
            if fault.activated and fault.fault_type in self._fault_paths
        ]
        if not mapped:
            return None
        fault = mapped[0]
        return ClassificationSignal(
            path=self._fault_paths[fault.fault_type],
            confidence=ClassificationConfidence.HIGH,
            score=1.0,
            source=ClassificationSource.DETERMINISTIC_FAULT,
            reason=f"Direct activated fault evidence identifies {fault.fault_type}.",
            evidence=(EvaluationEvidence(
                assertion="activated_fault_type",
                expected="deterministic fault mapping",
                observed=fault.fault_type,
                span_id=attribution.root_node_id,
                metadata={"fault_id": fault.fault_id},
            ),),
            fault_id=fault.fault_id,
        )

    def _grade_signals(self, grades: Sequence[GradeResult]) -> list[ClassificationSignal]:
        signals: list[ClassificationSignal] = []
        for grade in grades:
            if grade.verdict not in {Verdict.FAIL, Verdict.ERROR}:
                continue
            for evidence in grade.evidence:
                path = self._grade_paths.get(evidence.assertion)
                if path is None:
                    continue
                source = (
                    ClassificationSource.TRACE_STRUCTURE
                    if grade.grader_name == "trace_structure"
                    else ClassificationSource.DETERMINISTIC_GRADE
                )
                score = 0.75 if source == ClassificationSource.TRACE_STRUCTURE else 0.8
                confidence = (
                    ClassificationConfidence.MEDIUM
                    if source == ClassificationSource.TRACE_STRUCTURE
                    else ClassificationConfidence.HIGH
                )
                signals.append(ClassificationSignal(
                    path=path,
                    confidence=confidence,
                    score=score,
                    source=source,
                    reason=f"Failed deterministic assertion {evidence.assertion!r}.",
                    evidence=(evidence,),
                ))
        return signals

    def _unique_paths(self, signals: Sequence[ClassificationSignal | None]) -> list[FailureTaxonomyPath]:
        paths: list[FailureTaxonomyPath] = []
        seen: set[PathKey] = set()
        for signal in signals:
            if signal is None or signal.path in seen:
                continue
            seen.add(signal.path)
            paths.append(self._catalog.resolve(*signal.path))
        return paths
