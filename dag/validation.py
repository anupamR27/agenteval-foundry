from dag.models import EvaluationDAG


class DagValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("Invalid evaluation DAG: " + "; ".join(errors))


def validate_dag(dag: EvaluationDAG) -> EvaluationDAG:
    errors: list[str] = []
    node_ids = [node.node_id for node in dag.nodes]
    node_id_set = set(node_ids)
    if len(node_ids) != len(node_id_set):
        errors.append("duplicate node IDs")
    if dag.nodes and not dag.root_node_ids:
        errors.append("non-empty DAG has no root")
    if any(root not in node_id_set for root in dag.root_node_ids):
        errors.append("root references an unknown node")
    expected_roots = {node.node_id for node in dag.nodes if not node.parent_ids}
    if set(dag.root_node_ids) != expected_roots:
        errors.append("root node IDs are inconsistent with parent relationships")

    edge_pairs = {(edge.source_node_id, edge.target_node_id) for edge in dag.edges}
    for node in dag.nodes:
        if any(parent not in node_id_set for parent in node.parent_ids):
            errors.append(f"node {node.node_id} has an unknown parent")
        if any(child not in node_id_set for child in node.child_ids):
            errors.append(f"node {node.node_id} has an unknown child")
        for parent in node.parent_ids:
            if (parent, node.node_id) not in edge_pairs:
                errors.append(f"parent relationship for {node.node_id} has no edge")
        for child in node.child_ids:
            if (node.node_id, child) not in edge_pairs:
                errors.append(f"child relationship for {node.node_id} has no edge")

    for edge in dag.edges:
        if edge.source_node_id not in node_id_set or edge.target_node_id not in node_id_set:
            errors.append("edge references an unknown node")
            continue
        source = dag.node(edge.source_node_id)
        target = dag.node(edge.target_node_id)
        if edge.target_node_id not in source.child_ids:
            errors.append(f"edge target missing from children of {source.node_id}")
        if edge.source_node_id not in target.parent_ids:
            errors.append(f"edge source missing from parents of {target.node_id}")

    indegree = {node_id: 0 for node_id in node_ids}
    for edge in dag.edges:
        if edge.target_node_id in indegree and edge.source_node_id in node_id_set:
            indegree[edge.target_node_id] += 1
    queue = [node_id for node_id in node_ids if indegree[node_id] == 0]
    ordered = []
    while queue:
        current = queue.pop(0)
        ordered.append(current)
        for child in dag.node(current).child_ids:
            if child not in indegree:
                continue
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(ordered) != len(node_ids):
        errors.append("graph is cyclic or topological sorting failed")

    reachable: set[object] = set()
    pending = list(dag.root_node_ids)
    while pending:
        current = pending.pop(0)
        if current in reachable or current not in node_id_set:
            continue
        reachable.add(current)
        pending.extend(dag.node(current).child_ids)
    if reachable != node_id_set:
        errors.append("not all nodes are reachable from a root")
    if errors:
        raise DagValidationError(errors)
    for index, node_id in enumerate(ordered):
        dag.node(node_id).topological_index = index
    return dag
