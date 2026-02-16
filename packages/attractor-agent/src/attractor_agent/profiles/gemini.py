"""Gemini profile."""

from attractor_agent.profiles.base import ProviderProfile, build_default_registry


def create_gemini_profile(model: str = "gemini-2.5-pro") -> ProviderProfile:
    tool_names = ["read_file", "write_file", "edit_file", "shell", "grep", "glob"]
    return ProviderProfile(
        id="gemini",
        provider_name="gemini",
        model=model,
        base_prompt="You are a Gemini coding agent.",
        tool_registry=build_default_registry(include_apply_patch=False),
        default_tool_names=tool_names,
    )
