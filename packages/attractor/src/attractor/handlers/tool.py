from attractor.context import Context
from attractor.outcome import Outcome, StageStatus
from attractor.parser.ast import Node


def handle(node: Node, context: Context) -> Outcome:
    context.set("last_node", node.id)
    return Outcome(status=StageStatus.SUCCESS)
