from attractor.parser.ast import Edge, Graph, Node
from attractor.parser.parser import parse_dot


def test_parser_supports_nodes_edges_defaults_and_chains():
    dot = """
    digraph Flow {
      graph [rankdir=LR];
      node [shape=box];
      edge [color=gray];
      start [type=start, class=entry];
      step;
      finish [type=exit];
      start -> step -> finish [label=next, when="context.ok = yes"];
    }
    """

    graph = parse_dot(dot)

    assert isinstance(graph, Graph)
    assert graph.name == "Flow"
    assert graph.graph_attrs == {"rankdir": "LR"}
    assert graph.node_defaults == {"shape": "box"}
    assert graph.edge_defaults == {"color": "gray"}
    assert graph.nodes["start"] == Node(id="start", attrs={"type": "start", "class": "entry"})
    assert graph.nodes["step"] == Node(id="step", attrs={})
    assert len(graph.edges) == 2
    assert graph.edges[0] == Edge(
        source="start",
        target="step",
        attrs={"label": "next", "when": "context.ok = yes"},
    )
    assert graph.edges[1].source == "step"
    assert graph.edges[1].target == "finish"
