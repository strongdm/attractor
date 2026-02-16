from attractor.context import Context
from attractor.outcome import Outcome


def evaluate_condition(
    expression: str | None,
    context: Context,
    outcome: Outcome | None,
    preferred_label: str | None,
) -> bool:
    if expression is None or expression.strip() == "":
        return True

    clauses = [part.strip() for part in expression.split("&&")]
    for clause in clauses:
        if not _evaluate_clause(clause, context, outcome, preferred_label):
            return False
    return True


def _evaluate_clause(
    clause: str,
    context: Context,
    outcome: Outcome | None,
    preferred_label: str | None,
) -> bool:
    if "!=" in clause:
        left, right = clause.split("!=", 1)
        return _resolve_value(left.strip(), context, outcome, preferred_label) != _strip_quotes(
            right.strip()
        )

    if "=" in clause:
        left, right = clause.split("=", 1)
        return _resolve_value(left.strip(), context, outcome, preferred_label) == _strip_quotes(
            right.strip()
        )

    raise ValueError(f"Unsupported clause: {clause!r}")


def _resolve_value(
    key: str,
    context: Context,
    outcome: Outcome | None,
    preferred_label: str | None,
) -> str:
    if key.startswith("context."):
        value = context.get(key.split(".", 1)[1])
        return "" if value is None else str(value)
    if key == "outcome":
        return "" if outcome is None else outcome.status.value
    if key == "preferred_label":
        return "" if preferred_label is None else preferred_label
    return _strip_quotes(key)


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value
