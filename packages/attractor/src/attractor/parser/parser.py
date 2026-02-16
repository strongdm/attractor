from attractor.parser.ast import Edge, Graph, Node
from attractor.parser.lexer import Token, lex


class DotParser:
    def __init__(self, source: str):
        self._tokens = lex(source)
        self._index = 0

    def parse(self) -> Graph:
        self._expect_ident("digraph")
        name = "graph"
        if self._peek().kind in {"IDENT", "STRING"} and self._peek().value != "{":
            name = self._consume().value
        self._expect("LBRACE")
        graph = Graph(name=name)

        while self._peek().kind not in {"RBRACE", "EOF"}:
            self._parse_statement(graph)
            if self._peek().kind == "SEMICOLON":
                self._consume()

        self._expect("RBRACE")
        self._expect("EOF")
        return graph

    def _parse_statement(self, graph: Graph) -> None:
        token = self._peek()
        if token.kind not in {"IDENT", "STRING"}:
            raise ValueError(f"Expected statement at {token.position}")

        lead = self._consume().value
        if lead in {"graph", "node", "edge"} and self._peek().kind == "LBRACKET":
            attrs = self._parse_attr_list()
            if lead == "graph":
                graph.graph_attrs.update(attrs)
            elif lead == "node":
                graph.node_defaults.update(attrs)
            else:
                graph.edge_defaults.update(attrs)
            return

        if self._peek().kind == "ARROW":
            self._parse_edge_statement(graph, lead)
            return

        attrs = self._parse_attr_list(optional=True)
        node = graph.nodes.get(lead, Node(id=lead))
        node.attrs.update(attrs)
        graph.nodes[lead] = node

    def _parse_edge_statement(self, graph: Graph, first: str) -> None:
        chain = [first]
        while self._peek().kind == "ARROW":
            self._consume()
            chain.append(self._expect_value())

        attrs = self._parse_attr_list(optional=True)

        for node_id in chain:
            graph.nodes.setdefault(node_id, Node(id=node_id))
        for index in range(len(chain) - 1):
            graph.edges.append(
                Edge(source=chain[index], target=chain[index + 1], attrs=dict(attrs))
            )

    def _parse_attr_list(self, optional: bool = False) -> dict[str, str]:
        if optional and self._peek().kind != "LBRACKET":
            return {}

        attrs: dict[str, str] = {}
        while self._peek().kind == "LBRACKET":
            self._consume()
            while self._peek().kind != "RBRACKET":
                key = self._expect_value()
                self._expect("EQUALS")
                value = self._expect_value()
                attrs[key] = value
                if self._peek().kind in {"COMMA", "SEMICOLON"}:
                    self._consume()
            self._expect("RBRACKET")
        return attrs

    def _expect_value(self) -> str:
        token = self._peek()
        if token.kind not in {"IDENT", "STRING"}:
            raise ValueError(f"Expected value at {token.position}")
        return self._consume().value

    def _expect_ident(self, value: str) -> None:
        token = self._peek()
        if token.kind != "IDENT" or token.value != value:
            raise ValueError(f"Expected {value!r} at {token.position}")
        self._consume()

    def _expect(self, kind: str) -> Token:
        token = self._peek()
        if token.kind != kind:
            raise ValueError(f"Expected {kind} at {token.position}")
        return self._consume()

    def _peek(self) -> Token:
        return self._tokens[self._index]

    def _consume(self) -> Token:
        token = self._tokens[self._index]
        self._index += 1
        return token


def parse_dot(source: str) -> Graph:
    return DotParser(source).parse()
