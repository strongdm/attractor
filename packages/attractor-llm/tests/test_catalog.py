"""Tests for the model catalog."""

from attractor_llm.catalog import get_latest_model, get_model_info, list_models


class TestCatalog:
    def test_known_model(self):
        info = get_model_info("claude-opus-4-6")
        assert info is not None
        assert info.provider == "anthropic"
        assert info.supports_tools is True
        assert info.supports_reasoning is True

    def test_unknown_model(self):
        info = get_model_info("nonexistent-model-xyz")
        assert info is None

    def test_list_all_models(self):
        models = list_models()
        assert len(models) > 0
        providers = {m.provider for m in models}
        assert "openai" in providers
        assert "anthropic" in providers
        assert "gemini" in providers

    def test_list_by_provider(self):
        models = list_models(provider="anthropic")
        assert all(m.provider == "anthropic" for m in models)
        assert len(models) >= 2  # opus, sonnet at minimum

    def test_list_by_capability(self):
        models = list_models(supports_reasoning=True)
        assert all(m.supports_reasoning for m in models)

    def test_alias_lookup(self):
        """Models should be findable by alias."""
        info = get_model_info("claude-opus-4-6")
        assert info is not None
        # Also check via aliases if any
        for alias in info.aliases:
            found = get_model_info(alias)
            assert found is not None
            assert found.id == info.id

    def test_get_latest_model_for_provider(self):
        info = get_latest_model("anthropic")
        assert info is not None
        assert info.provider == "anthropic"

    def test_get_latest_model_for_unknown_provider_returns_none(self):
        assert get_latest_model("unknown-provider") is None
