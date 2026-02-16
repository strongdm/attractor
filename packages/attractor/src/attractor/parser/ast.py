from dataclasses import dataclass, field


@dataclass(slots=True)
class Node:
    id: str
    attrs: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Edge:
    source: str
    target: str
    attrs: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Graph:
    name: str
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    graph_attrs: dict[str, str] = field(default_factory=dict)
    node_defaults: dict[str, str] = field(default_factory=dict)
    edge_defaults: dict[str, str] = field(default_factory=dict)
