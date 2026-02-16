"""Shell tool."""

from __future__ import annotations

from typing import Any

from attractor_llm.request import ToolDefinition

from attractor_agent.execution import LocalExecutionEnvironment
from attractor_agent.tools.registry import RegisteredTool


def _execute(args: dict[str, Any], env: LocalExecutionEnvironment) -> str:
    command = args["command"]
    timeout_ms = int(args.get("timeout_ms", 10_000))
    result = env.exec_command(command=command, timeout_ms=timeout_ms)
    chunks = [result.stdout.rstrip(), result.stderr.rstrip(), f"exit_code: {result.exit_code}"]
    if result.timed_out:
        chunks.append(f"[ERROR: Command timed out after {timeout_ms}ms]")
    return "\n".join(chunk for chunk in chunks if chunk)


def shell_tool() -> RegisteredTool:
    return RegisteredTool(
        definition=ToolDefinition(
            name="shell",
            description="Execute a shell command.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout_ms": {"type": "integer"},
                    "description": {"type": "string"},
                },
                "required": ["command"],
            },
        ),
        executor=_execute,
    )
