"""Provider profile abstraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from attractor_llm.request import ToolDefinition

from attractor_agent.tools.apply_patch import apply_patch_tool
from attractor_agent.tools.edit_file import edit_file_tool
from attractor_agent.tools.glob import glob_tool
from attractor_agent.tools.grep import grep_tool
from attractor_agent.tools.read_file import read_file_tool
from attractor_agent.tools.registry import ToolRegistry
from attractor_agent.tools.shell import shell_tool
from attractor_agent.tools.write_file import write_file_tool


def build_default_registry(include_apply_patch: bool) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(read_file_tool())
    registry.register(write_file_tool())
    registry.register(shell_tool())
    registry.register(grep_tool())
    registry.register(glob_tool())
    if include_apply_patch:
        registry.register(apply_patch_tool())
    else:
        registry.register(edit_file_tool())
    return registry


@dataclass
class ProviderProfile:
    id: str
    provider_name: str
    model: str
    base_prompt: str
    tool_registry: ToolRegistry
    default_tool_names: list[str]
    supports_parallel_tool_calls: bool = False
    context_window_size: int = 200_000
    _provider_options: dict[str, Any] | None = field(default=None)

    def build_system_prompt(self) -> str:
        return self.base_prompt

    def tools(self) -> list[ToolDefinition]:
        result = []
        for name in self.default_tool_names:
            tool = self.tool_registry.get(name)
            if tool is not None:
                result.append(tool.definition)
        return result

    def provider_options(self) -> dict[str, Any] | None:
        return self._provider_options
