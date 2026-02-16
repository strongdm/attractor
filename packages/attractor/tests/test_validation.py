from attractor.parser.ast import Edge, Graph, Node
from attractor.validation import validate_graph


def test_validation_reports_core_errors_and_unreachable_warning():
    graph = Graph(
        name="Flow",
        nodes={
            "start": Node(id="start", attrs={"type": "start"}),
            "work": Node(id="work", attrs={}),
            "exit": Node(id="exit", attrs={"type": "exit"}),
            "orphan": Node(id="orphan", attrs={}),
        },
        edges=[
            Edge(source="start", target="work", attrs={}),
            Edge(source="work", target="missing", attrs={}),
            Edge(source="exit", target="work", attrs={}),
        ],
    )

    result = validate_graph(graph, strict_reachability=False)

    assert any("referenced target does not exist: missing" in error for error in result.errors)
    assert any("exit node must have no outgoing edges" in error for error in result.errors)
    assert any("unreachable node: orphan" in warning for warning in result.warnings)


def test_validation_enforces_single_valid_start_node():
    graph = Graph(name="Bad", nodes={"n1": Node(id="n1", attrs={})}, edges=[])

    result = validate_graph(graph)

    assert any("start node is required" in error for error in result.errors)
