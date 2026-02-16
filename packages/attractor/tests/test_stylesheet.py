from attractor.parser.ast import Node
from attractor.stylesheet import parse_stylesheet
from attractor.transforms import apply_stylesheet_to_node


def test_stylesheet_applies_with_selector_specificity():
    stylesheet = parse_stylesheet(
        """
        * { timeout: 10; handler: manager_loop; }
        .entry { timeout: 7; }
        #start { timeout: 3; }
        """
    )
    node = Node(id="start", attrs={"class": "entry"})

    merged = apply_stylesheet_to_node(node, stylesheet)

    assert merged["handler"] == "manager_loop"
    assert merged["timeout"] == "3"
