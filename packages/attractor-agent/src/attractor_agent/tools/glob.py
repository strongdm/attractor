"""Glob tool."""

from __future__ import annotations

from typing import Any

from attractor_llm.request import ToolDefinition

from attractor_agent.execution import LocalExecutionEnvironment
from attractor_agent.tools.registry import RegisteredTool


def _execute(args: dict[str, Any], env: LocalExecutionEnvironment) -> str:
    matches = env.glob(pattern=args["pattern"], path=args.get("path", "."))
    return "\n".join(matches)


def glob_tool() -> RegisteredTool:
    return RegisteredTool(
        definition=ToolDefinition(
            name="glob",
            description="Find files matching a glob pattern.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string"},
                },
                "required": ["pattern"],
            },
        ),
        executor=_execute,
    )
