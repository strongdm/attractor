"""Minimal apply_patch tool with add/update/delete support."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from attractor_llm.request import ToolDefinition

from attractor_agent.execution import LocalExecutionEnvironment
from attractor_agent.tools.registry import RegisteredTool


@dataclass
class _Operation:
    kind: str
    path: str
    body: list[str]


def _parse_patch(patch: str) -> list[_Operation]:
    lines = patch.splitlines()
    if not lines or lines[0].strip() != "*** Begin Patch":
        raise ValueError("Patch must start with *** Begin Patch")
    if lines[-1].strip() != "*** End Patch":
        raise ValueError("Patch must end with *** End Patch")

    operations: list[_Operation] = []
    current: _Operation | None = None
    for line in lines[1:-1]:
        if line.startswith("*** Add File: "):
            if current is not None:
                operations.append(current)
            current = _Operation("add", line.removeprefix("*** Add File: ").strip(), [])
        elif line.startswith("*** Update File: "):
            if current is not None:
                operations.append(current)
            current = _Operation("update", line.removeprefix("*** Update File: ").strip(), [])
        elif line.startswith("*** Delete File: "):
            if current is not None:
                operations.append(current)
            current = _Operation("delete", line.removeprefix("*** Delete File: ").strip(), [])
        else:
            if current is None:
                continue
            current.body.append(line)

    if current is not None:
        operations.append(current)
    return operations


def _apply_update(original: str, body: list[str]) -> str:
    relevant = [line for line in body if line and not line.startswith("@@")]
    if relevant and all(line.startswith("+") for line in relevant):
        return "\n".join(line[1:] for line in relevant) + "\n"

    current = original
    old_lines = [line[1:] for line in relevant if line.startswith(" ") or line.startswith("-")]
    new_lines = [line[1:] for line in relevant if line.startswith(" ") or line.startswith("+")]
    old_chunk = "\n".join(old_lines)
    new_chunk = "\n".join(new_lines)
    if old_chunk and original.endswith("\n"):
        old_chunk += "\n"
        new_chunk += "\n"

    index = current.find(old_chunk)
    if index < 0:
        raise ValueError("Update hunk did not match file content")
    return current[:index] + new_chunk + current[index + len(old_chunk) :]


def _execute(args: dict[str, Any], env: LocalExecutionEnvironment) -> str:
    operations = _parse_patch(args["patch"])
    outputs: list[str] = []

    for op in operations:
        target = env.resolve_path(op.path)
        if op.kind == "add":
            if target.exists():
                raise ValueError(f"File already exists: {op.path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            content = "\n".join(line[1:] for line in op.body if line.startswith("+"))
            target.write_text(content + "\n", encoding="utf-8")
            outputs.append(f"Added {op.path}")
            continue

        if op.kind == "delete":
            if target.exists():
                target.unlink()
            outputs.append(f"Deleted {op.path}")
            continue

        if op.kind == "update":
            if not target.exists():
                raise ValueError(f"File not found: {op.path}")
            original = target.read_text(encoding="utf-8")
            updated = _apply_update(original, op.body)
            target.write_text(updated, encoding="utf-8")
            outputs.append(f"Updated {op.path}")

    return "\n".join(outputs)


def apply_patch_tool() -> RegisteredTool:
    return RegisteredTool(
        definition=ToolDefinition(
            name="apply_patch",
            description="Apply code changes using patch format.",
            parameters={
                "type": "object",
                "properties": {
                    "patch": {"type": "string"},
                },
                "required": ["patch"],
            },
        ),
        executor=_execute,
    )
