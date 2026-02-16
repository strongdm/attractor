"""Tool output truncation helpers."""

from __future__ import annotations

DEFAULT_TOOL_CHAR_LIMITS = {
    "read_file": 50_000,
    "shell": 30_000,
    "grep": 20_000,
    "glob": 20_000,
    "edit_file": 10_000,
    "apply_patch": 10_000,
    "write_file": 1_000,
}

DEFAULT_TOOL_LINE_LIMITS = {
    "shell": 256,
    "grep": 200,
    "glob": 500,
}

DEFAULT_TOOL_MODES = {
    "read_file": "head_tail",
    "shell": "head_tail",
    "grep": "tail",
    "glob": "tail",
    "edit_file": "tail",
    "apply_patch": "tail",
    "write_file": "tail",
}


def truncate_output(output: str, max_chars: int, mode: str = "head_tail") -> str:
    if max_chars <= 0 or len(output) <= max_chars:
        return output

    if mode == "tail":
        removed = len(output) - max_chars
        return (
            "[WARNING: Tool output was truncated. First "
            f"{removed} characters were removed. The full output is available in the event stream.]\n\n"
            f"{output[-max_chars:]}"
        )

    head_chars = max_chars // 2
    tail_chars = max_chars - head_chars
    removed = len(output) - max_chars
    return (
        f"{output[:head_chars]}\n\n"
        "[WARNING: Tool output was truncated. "
        f"{removed} characters were removed from the middle. "
        "The full output is available in the event stream. "
        "If you need to see specific parts, re-run the tool with more targeted parameters.]\n\n"
        f"{output[-tail_chars:]}"
    )


def truncate_lines(output: str, max_lines: int) -> str:
    if max_lines <= 0:
        return output

    lines = output.splitlines()
    if len(lines) <= max_lines:
        return output

    head_count = max_lines // 2
    tail_count = max_lines - head_count
    omitted = len(lines) - head_count - tail_count
    kept = lines[:head_count] + [f"[... {omitted} lines omitted ...]"] + lines[-tail_count:]
    if "[WARNING:" in output and not any(line.startswith("[WARNING:") for line in kept):
        warning_line = next((line for line in lines if line.startswith("[WARNING:")), None)
        if warning_line is not None:
            kept.insert(0, warning_line)
    return "\n".join(kept)


def truncate_tool_output(
    output: str,
    tool_name: str,
    tool_char_limits: dict[str, int] | None = None,
    tool_line_limits: dict[str, int] | None = None,
) -> str:
    char_limits = DEFAULT_TOOL_CHAR_LIMITS | (tool_char_limits or {})
    line_limits = DEFAULT_TOOL_LINE_LIMITS | (tool_line_limits or {})
    mode = DEFAULT_TOOL_MODES.get(tool_name, "head_tail")
    max_chars = char_limits.get(tool_name, 10_000)

    result = truncate_output(output, max_chars=max_chars, mode=mode)
    max_lines = line_limits.get(tool_name)
    if max_lines is not None:
        result = truncate_lines(result, max_lines=max_lines)
    return result
