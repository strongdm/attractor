from attractor.parser.ast import Graph, Node
from attractor.stylesheet import Stylesheet


def apply_stylesheet(graph: Graph, stylesheet: Stylesheet) -> Graph:
    for node_id, node in list(graph.nodes.items()):
        merged = apply_stylesheet_to_node(node, stylesheet)
        graph.nodes[node_id] = Node(id=node.id, attrs=merged)
    return graph


def apply_stylesheet_to_node(node: Node, stylesheet: Stylesheet) -> dict[str, str]:
    merged = dict(node.attrs)
    sorted_rules = sorted(stylesheet.rules, key=lambda rule: (rule.specificity, rule.order))
    for rule in sorted_rules:
        if _matches(node, rule.selector):
            merged.update(rule.declarations)
    return merged


def _matches(node: Node, selector: str) -> bool:
    if selector == "*":
        return True
    if selector.startswith("#"):
        return node.id == selector[1:]
    if selector.startswith("."):
        classes = node.attrs.get("class", "").split()
        return selector[1:] in classes
    return False
