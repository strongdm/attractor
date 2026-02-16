"""Write-file tool."""

from __future__ import annotations

from typing import Any

from attractor_llm.request import ToolDefinition

from attractor_agent.execution import LocalExecutionEnvironment
from attractor_agent.tools.registry import RegisteredTool


def _execute(args: dict[str, Any], env: LocalExecutionEnvironment) -> str:
    bytes_written = env.write_file(args["file_path"], args["content"])
    return f"Written {bytes_written} bytes to {args['file_path']}"


def write_file_tool() -> RegisteredTool:
    return RegisteredTool(
        definition=ToolDefinition(
            name="write_file",
            description="Write content to a file.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["file_path", "content"],
            },
        ),
        executor=_execute,
    )
