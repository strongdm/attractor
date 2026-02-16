"""Anthropic profile."""

from attractor_agent.profiles.base import ProviderProfile, build_default_registry


def create_anthropic_profile(model: str = "claude-sonnet-4.5") -> ProviderProfile:
    tool_names = ["read_file", "write_file", "edit_file", "shell", "grep", "glob"]
    return ProviderProfile(
        id="anthropic",
        provider_name="anthropic",
        model=model,
        base_prompt="You are an Anthropic coding agent.",
        tool_registry=build_default_registry(include_apply_patch=False),
        default_tool_names=tool_names,
    )
