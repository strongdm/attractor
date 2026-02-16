"""Grep tool."""

from __future__ import annotations

from typing import Any

from attractor_llm.request import ToolDefinition

from attractor_agent.execution import LocalExecutionEnvironment
from attractor_agent.tools.registry import RegisteredTool


def _execute(args: dict[str, Any], env: LocalExecutionEnvironment) -> str:
    return env.grep(
        pattern=args["pattern"],
        path=args.get("path", "."),
        glob_filter=args.get("glob_filter"),
        case_insensitive=bool(args.get("case_insensitive", False)),
        max_results=int(args.get("max_results", 100)),
    )


def grep_tool() -> RegisteredTool:
    return RegisteredTool(
        definition=ToolDefinition(
            name="grep",
            description="Search file contents using regex patterns.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string"},
                    "glob_filter": {"type": "string"},
                    "case_insensitive": {"type": "boolean"},
                    "max_results": {"type": "integer"},
                },
                "required": ["pattern"],
            },
        ),
        executor=_execute,
    )
