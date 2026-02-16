from attractor.context import Context
from attractor.handlers import create_default_registry
from attractor.outcome import StageStatus
from attractor.parser.ast import Node


def test_default_handlers_are_registered_and_return_outcomes():
    registry = create_default_registry()
    context = Context({})

    start = registry.get("start")(Node(id="start", attrs={}), context)
    wait = registry.get("wait_human")(Node(id="wait", attrs={"label": "clarify"}), context)
    done = registry.get("exit")(Node(id="done", attrs={}), context)

    assert start.status is StageStatus.SUCCESS
    assert wait.status is StageStatus.WAITING
    assert wait.preferred_label == "clarify"
    assert done.status is StageStatus.EXITED
