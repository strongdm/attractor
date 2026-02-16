from dataclasses import dataclass, field

from attractor.parser.ast import Graph


@dataclass(slots=True)
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_graph(graph: Graph, strict_reachability: bool = False) -> ValidationResult:
    result = ValidationResult()

    start_nodes = [node for node in graph.nodes.values() if node.attrs.get("type") == "start"]
    if not start_nodes:
        result.errors.append("start node is required")
        start_node_id = None
    else:
        start_node_id = start_nodes[0].id

    incoming: dict[str, int] = {node_id: 0 for node_id in graph.nodes}
    outgoing: dict[str, int] = {node_id: 0 for node_id in graph.nodes}

    for edge in graph.edges:
        if edge.target not in graph.nodes:
            result.errors.append(f"referenced target does not exist: {edge.target}")
        if edge.source not in graph.nodes:
            result.errors.append(f"referenced source does not exist: {edge.source}")
        if edge.source in outgoing:
            outgoing[edge.source] += 1
        if edge.target in incoming:
            incoming[edge.target] += 1

    if start_node_id is not None and incoming.get(start_node_id, 0) > 0:
        result.errors.append("start node must have no incoming edges")

    for node_id, node in graph.nodes.items():
        if node.attrs.get("type") == "exit" and outgoing.get(node_id, 0) > 0:
            result.errors.append("exit node must have no outgoing edges")

    if start_node_id is not None:
        reachable = _reachable_nodes(graph, start_node_id)
        for node_id in graph.nodes:
            if node_id not in reachable:
                message = f"unreachable node: {node_id}"
                if strict_reachability:
                    result.errors.append(message)
                else:
                    result.warnings.append(message)

    return result


def _reachable_nodes(graph: Graph, start_node_id: str) -> set[str]:
    visited: set[str] = set()
    queue = [start_node_id]

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        for edge in graph.edges:
            if edge.source == current and edge.target in graph.nodes:
                queue.append(edge.target)

    return visited
