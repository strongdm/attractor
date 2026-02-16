from attractor.context import Context
from attractor.engine import ExecutionEngine
from attractor.handlers import create_default_registry
from attractor.outcome import StageStatus
from attractor.parser.ast import Edge, Graph, Node


def test_engine_runs_start_to_exit():
    graph = Graph(
        name="Flow",
        nodes={
            "start": Node(id="start", attrs={"type": "start", "handler": "start"}),
            "task": Node(id="task", attrs={"handler": "manager_loop"}),
            "exit": Node(id="exit", attrs={"type": "exit", "handler": "exit"}),
        },
        edges=[
            Edge(source="start", target="task", attrs={}),
            Edge(source="task", target="exit", attrs={"when": "outcome = success"}),
        ],
    )

    engine = ExecutionEngine(handler_registry=create_default_registry())
    result = engine.execute(graph, Context({}))

    assert result.outcome.status is StageStatus.EXITED
    assert result.visited_nodes == ["start", "task", "exit"]


def test_engine_uses_preferred_label_fallback():
    graph = Graph(
        name="Flow",
        nodes={
            "start": Node(id="start", attrs={"type": "start", "handler": "start"}),
            "router": Node(id="router", attrs={"handler": "wait_human", "label": "path_b"}),
            "a": Node(id="a", attrs={"handler": "manager_loop"}),
            "b": Node(id="b", attrs={"handler": "manager_loop"}),
            "exit": Node(id="exit", attrs={"type": "exit", "handler": "exit"}),
        },
        edges=[
            Edge(source="start", target="router", attrs={}),
            Edge(source="router", target="a", attrs={"label": "path_a"}),
            Edge(source="router", target="b", attrs={"label": "path_b"}),
            Edge(source="a", target="exit", attrs={}),
            Edge(source="b", target="exit", attrs={}),
        ],
    )

    engine = ExecutionEngine(handler_registry=create_default_registry())
    result = engine.execute(graph, Context({}))

    assert result.visited_nodes == ["start", "router", "b", "exit"]
