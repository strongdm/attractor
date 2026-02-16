"""Edit-file tool using exact replacement semantics."""

from __future__ import annotations

from typing import Any

from attractor_llm.request import ToolDefinition

from attractor_agent.execution import LocalExecutionEnvironment
from attractor_agent.tools.registry import RegisteredTool


def _execute(args: dict[str, Any], env: LocalExecutionEnvironment) -> str:
    file_path = args["file_path"]
    old_string = args["old_string"]
    new_string = args["new_string"]
    replace_all = bool(args.get("replace_all", False))

    content = env.read_text(file_path)
    occurrences = content.count(old_string)
    if occurrences == 0:
        raise ValueError("old_string not found")
    if occurrences > 1 and not replace_all:
        raise ValueError("old_string matches multiple locations")

    if replace_all:
        updated = content.replace(old_string, new_string)
        replaced = occurrences
    else:
        updated = content.replace(old_string, new_string, 1)
        replaced = 1
    env.write_text(file_path, updated)
    noun = "replacement" if replaced == 1 else "replacements"
    return f"Applied {replaced} {noun} in {file_path}"


def edit_file_tool() -> RegisteredTool:
    return RegisteredTool(
        definition=ToolDefinition(
            name="edit_file",
            description="Replace an exact string occurrence in a file.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                    "replace_all": {"type": "boolean"},
                },
                "required": ["file_path", "old_string", "new_string"],
            },
        ),
        executor=_execute,
    )
