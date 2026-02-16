"""OpenAI profile."""

from attractor_agent.profiles.base import ProviderProfile, build_default_registry


def create_openai_profile(model: str = "gpt-5.2-codex") -> ProviderProfile:
    tool_names = ["read_file", "apply_patch", "write_file", "shell", "grep", "glob"]
    return ProviderProfile(
        id="openai",
        provider_name="openai",
        model=model,
        base_prompt="You are an OpenAI coding agent.",
        tool_registry=build_default_registry(include_apply_patch=True),
        default_tool_names=tool_names,
        supports_parallel_tool_calls=True,
    )
