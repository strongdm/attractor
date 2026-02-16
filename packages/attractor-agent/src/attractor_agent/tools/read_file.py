"""Read-file tool."""

from __future__ import annotations

from typing import Any

from attractor_llm.request import ToolDefinition

from attractor_agent.execution import LocalExecutionEnvironment
from attractor_agent.tools.registry import RegisteredTool


def _execute(args: dict[str, Any], env: LocalExecutionEnvironment) -> str:
    return env.read_file(
        args["file_path"],
        offset=args.get("offset"),
        limit=args.get("limit"),
    )


def read_file_tool() -> RegisteredTool:
    return RegisteredTool(
        definition=ToolDefinition(
            name="read_file",
            description="Read a file from the filesystem.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "offset": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
                "required": ["file_path"],
            },
        ),
        executor=_execute,
    )
