from dataclasses import dataclass, field


@dataclass(slots=True)
class Rule:
    selector: str
    declarations: dict[str, str]
    specificity: int
    order: int


@dataclass(slots=True)
class Stylesheet:
    rules: list[Rule] = field(default_factory=list)


def parse_stylesheet(source: str) -> Stylesheet:
    rules: list[Rule] = []
    chunks = source.split("}")

    for order, chunk in enumerate(chunks):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "{" not in chunk:
            raise ValueError(f"Invalid stylesheet block: {chunk!r}")
        selector_text, declaration_text = chunk.split("{", 1)
        selector = selector_text.strip()
        declarations = _parse_declarations(declaration_text)
        rules.append(
            Rule(
                selector=selector,
                declarations=declarations,
                specificity=_selector_specificity(selector),
                order=order,
            )
        )

    return Stylesheet(rules=rules)


def _parse_declarations(text: str) -> dict[str, str]:
    declarations: dict[str, str] = {}
    for part in text.split(";"):
        item = part.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"Invalid declaration: {item!r}")
        key, value = item.split(":", 1)
        declarations[key.strip()] = value.strip()
    return declarations


def _selector_specificity(selector: str) -> int:
    if selector == "*":
        return 0
    if selector.startswith("."):
        return 10
    if selector.startswith("#"):
        return 100
    raise ValueError(f"Unsupported selector: {selector!r}")
