from dataclasses import dataclass, field
from typing import Callable, TypeVar

from attractor.condition import evaluate_condition
from attractor.context import Context
from attractor.handlers import HandlerRegistry, create_default_registry
from attractor.outcome import Outcome, StageStatus
from attractor.parser.ast import Edge, Graph, Node

T = TypeVar("T")


@dataclass(slots=True)
class ExecutionResult:
    outcome: Outcome
    visited_nodes: list[str] = field(default_factory=list)


class ExecutionEngine:
    def __init__(self, handler_registry: HandlerRegistry | None = None):
        self._handlers = handler_registry or create_default_registry()

    def execute(self, graph: Graph, context: Context) -> ExecutionResult:
        current = _find_start_node(graph)
        visited: list[str] = []
        outcome = Outcome(status=StageStatus.FAILURE, message="start node not found")

        if current is None:
            return ExecutionResult(outcome=outcome, visited_nodes=visited)

        while current is not None:
            visited.append(current.id)
            handler = self._handlers.get(_handler_name(current))
            retries = int(current.attrs.get("retries", "0"))
            outcome = retry_helper(lambda: handler(current, context), retries=retries)

            if outcome.status is StageStatus.FAILURE:
                break

            if current.attrs.get("type") == "exit" or outcome.status is StageStatus.EXITED:
                break

            next_edge = _select_next_edge(graph, current.id, context, outcome)
            if next_edge is None:
                break
            current = graph.nodes[next_edge.target]

        return ExecutionResult(outcome=outcome, visited_nodes=visited)


def retry_helper(operation: Callable[[], T], retries: int = 0) -> T:
    attempts = 0
    while True:
        try:
            return operation()
        except Exception:
            attempts += 1
            if attempts > retries:
                raise


def _find_start_node(graph: Graph) -> Node | None:
    for node in graph.nodes.values():
        if node.attrs.get("type") == "start":
            return node
    return graph.nodes.get("start")


def _handler_name(node: Node) -> str:
    if "handler" in node.attrs:
        return node.attrs["handler"]
    if node.attrs.get("type") == "start":
        return "start"
    if node.attrs.get("type") == "exit":
        return "exit"
    return "manager_loop"


def _select_next_edge(
    graph: Graph, node_id: str, context: Context, outcome: Outcome
) -> Edge | None:
    outgoing = [edge for edge in graph.edges if edge.source == node_id]
    if not outgoing:
        return None

    preferred = outcome.preferred_label
    if preferred is not None:
        for edge in outgoing:
            if edge.attrs.get("label") == preferred and _edge_matches(edge, context, outcome):
                return edge

    for edge in outgoing:
        if _edge_matches(edge, context, outcome):
            return edge

    return None


def _edge_matches(edge: Edge, context: Context, outcome: Outcome) -> bool:
    expression = edge.attrs.get("when")
    return evaluate_condition(expression, context, outcome, outcome.preferred_label)
