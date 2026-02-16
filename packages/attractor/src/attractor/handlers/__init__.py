from collections.abc import Callable

from attractor.context import Context
from attractor.outcome import Outcome
from attractor.parser.ast import Node

from attractor.handlers import (
    codergen,
    conditional,
    exit,
    fan_in,
    manager_loop,
    parallel,
    start,
    tool,
    wait_human,
)

Handler = Callable[[Node, Context], Outcome]


class HandlerRegistry:
    def __init__(self):
        self._handlers: dict[str, Handler] = {}

    def register(self, name: str, handler: Handler) -> None:
        self._handlers[name] = handler

    def get(self, name: str) -> Handler:
        if name not in self._handlers:
            raise KeyError(f"Unknown handler: {name}")
        return self._handlers[name]


def create_default_registry() -> HandlerRegistry:
    registry = HandlerRegistry()
    registry.register("start", start.handle)
    registry.register("exit", exit.handle)
    registry.register("codergen", codergen.handle)
    registry.register("wait_human", wait_human.handle)
    registry.register("conditional", conditional.handle)
    registry.register("parallel", parallel.handle)
    registry.register("fan_in", fan_in.handle)
    registry.register("tool", tool.handle)
    registry.register("manager_loop", manager_loop.handle)
    return registry
