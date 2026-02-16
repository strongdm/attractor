"""Tool registry and execution dispatcher."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from attractor_llm.request import ToolDefinition

from attractor_agent.execution import LocalExecutionEnvironment

ToolExecutor = Callable[[dict[str, Any], LocalExecutionEnvironment], str | Awaitable[str]]


@dataclass(frozen=True)
class RegisteredTool:
    definition: ToolDefinition
    executor: ToolExecutor


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, tool: RegisteredTool) -> None:
        self._tools[tool.definition.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> RegisteredTool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools.keys())

    def definitions(self) -> list[ToolDefinition]:
        return [self._tools[name].definition for name in self.names()]

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        execution_env: LocalExecutionEnvironment,
    ) -> str:
        tool = self.get(name)
        if tool is None:
            raise ValueError(f"Unknown tool: {name}")

        result = tool.executor(arguments, execution_env)
        if inspect.isawaitable(result):
            return await result
        return result
