from collections.abc import Sequence
from copy import deepcopy

from dag.models import EvaluationDAG, EvaluationDagEdge, EvaluationDagNode
from evaluation.models import EvaluationReport
from faults.models import FaultActivationRecord
from tracing.models import ExecutionTrace, TraceNodeType


class EvaluationDAGBuilder:
    def build(
        self,
        trace: ExecutionTrace,
        evaluation_report: EvaluationReport,
        fault_activation_records: Sequence[FaultActivationRecord] = (),
    ) -> EvaluationDAG:
        nodes = [
            EvaluationDagNode(
                node_id=span.span_id,
                trace_id=span.trace_id,
                parent_ids=[span.parent_span_id] if span.parent_span_id is not None else [],
                node_type=span.node_type,
                name=span.name,
                execution_status=span.status,
                metadata=deepcopy(span.metadata),
            )
            for span in trace.spans
        ]
        node_by_id = {node.node_id: node for node in nodes}
        edges: list[EvaluationDagEdge] = []
        for node in nodes:
            for parent_id in node.parent_ids:
                edges.append(EvaluationDagEdge(
                    source_node_id=parent_id,
                    target_node_id=node.node_id,
                ))
                if parent_id in node_by_id:
                    node_by_id[parent_id].child_ids.append(node.node_id)

        unscoped_grades = []
        for grade in evaluation_report.grades:
            if grade.target_span_id is not None and grade.target_span_id in node_by_id:
                node_by_id[grade.target_span_id].attached_grades.append(grade.model_copy(deep=True))
            else:
                unscoped_grades.append(grade.model_copy(deep=True))

        tool_nodes: dict[str, list[EvaluationDagNode]] = {}
        for node in nodes:
            if node.node_type == TraceNodeType.TOOL_EXECUTION:
                tool_nodes.setdefault(node.name, []).append(node)
        matched_nodes: set[object] = set()
        for fault in fault_activation_records:
            if not fault.activated:
                continue
            candidates = tool_nodes.get(fault.target_tool, [])
            indexed = candidates[fault.call_number - 1] if 0 < fault.call_number <= len(candidates) else None
            target = indexed if indexed is not None and indexed.node_id not in matched_nodes else next(
                (node for node in candidates if node.node_id not in matched_nodes),
                None,
            )
            if target is not None:
                target.attached_faults.append(fault.model_copy(deep=True))
                matched_nodes.add(target.node_id)

        roots = [node.node_id for node in nodes if not node.parent_ids]
        return EvaluationDAG(
            trace_id=trace.trace_id,
            run_id=trace.run_id,
            nodes=nodes,
            edges=edges,
            root_node_ids=roots,
            unscoped_grades=unscoped_grades,
        )
