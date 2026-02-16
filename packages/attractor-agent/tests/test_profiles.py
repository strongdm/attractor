from attractor_agent.profiles.anthropic import create_anthropic_profile
from attractor_agent.profiles.gemini import create_gemini_profile
from attractor_agent.profiles.openai import create_openai_profile


def test_openai_profile_has_apply_patch_tool():
    profile = create_openai_profile(model="gpt-test")
    tool_names = [tool.name for tool in profile.tools()]

    assert profile.id == "openai"
    assert profile.provider_name == "openai"
    assert "apply_patch" in tool_names


def test_anthropic_and_gemini_default_tools():
    anthropic = create_anthropic_profile(model="claude-test")
    gemini = create_gemini_profile(model="gemini-test")

    anthropic_names = [tool.name for tool in anthropic.tools()]
    gemini_names = [tool.name for tool in gemini.tools()]

    assert "edit_file" in anthropic_names
    assert "apply_patch" not in anthropic_names
    assert "write_file" in gemini_names
