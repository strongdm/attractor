package unifiedllm

import "testing"

func TestGetModelInfo(t *testing.T) {
	// By exact ID.
	info := GetModelInfo("claude-opus-4-6")
	if info == nil {
		t.Fatal("expected to find claude-opus-4-6")
	}
	if info.Provider != "anthropic" {
		t.Errorf("expected provider %q, got %q", "anthropic", info.Provider)
	}
	if info.ContextWindow != 200000 {
		t.Errorf("expected context window 200000, got %d", info.ContextWindow)
	}
	if !info.SupportsTools {
		t.Error("expected supports_tools = true")
	}

	// By alias.
	info = GetModelInfo("opus")
	if info == nil {
		t.Fatal("expected to find model by alias 'opus'")
	}
	if info.ID != "claude-opus-4-6" {
		t.Errorf("expected id %q, got %q", "claude-opus-4-6", info.ID)
	}

	// Unknown model.
	info = GetModelInfo("nonexistent-model")
	if info != nil {
		t.Errorf("expected nil for unknown model, got %v", info)
	}
}

func TestListModels(t *testing.T) {
	all := ListModels("")
	if len(all) != len(Models) {
		t.Errorf("expected %d models, got %d", len(Models), len(all))
	}

	anthropic := ListModels("anthropic")
	if len(anthropic) != 2 {
		t.Errorf("expected 2 Anthropic models, got %d", len(anthropic))
	}
	for _, m := range anthropic {
		if m.Provider != "anthropic" {
			t.Errorf("expected provider anthropic, got %q", m.Provider)
		}
	}

	openai := ListModels("openai")
	if len(openai) != 3 {
		t.Errorf("expected 3 OpenAI models, got %d", len(openai))
	}

	gemini := ListModels("gemini")
	if len(gemini) != 2 {
		t.Errorf("expected 2 Gemini models, got %d", len(gemini))
	}

	empty := ListModels("nonexistent")
	if len(empty) != 0 {
		t.Errorf("expected 0 models for nonexistent provider, got %d", len(empty))
	}
}

func TestGetLatestModel(t *testing.T) {
	info := GetLatestModel("anthropic", "")
	if info == nil {
		t.Fatal("expected to find latest Anthropic model")
	}
	if info.ID != "claude-opus-4-6" {
		t.Errorf("expected %q, got %q", "claude-opus-4-6", info.ID)
	}

	info = GetLatestModel("openai", "reasoning")
	if info == nil {
		t.Fatal("expected to find OpenAI reasoning model")
	}
	if info.Provider != "openai" {
		t.Errorf("expected provider openai, got %q", info.Provider)
	}
	if !info.SupportsReasoning {
		t.Error("expected supports_reasoning = true")
	}

	info = GetLatestModel("nonexistent", "")
	if info != nil {
		t.Errorf("expected nil for nonexistent provider, got %v", info)
	}
}

func TestModelInfoFields(t *testing.T) {
	for _, m := range Models {
		if m.ID == "" {
			t.Error("model ID must not be empty")
		}
		if m.Provider == "" {
			t.Errorf("model %q: provider must not be empty", m.ID)
		}
		if m.DisplayName == "" {
			t.Errorf("model %q: display_name must not be empty", m.ID)
		}
		if m.ContextWindow <= 0 {
			t.Errorf("model %q: context_window must be positive", m.ID)
		}
	}
}
