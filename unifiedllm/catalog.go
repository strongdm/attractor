package unifiedllm

// ModelInfo describes a known model in the catalog.
type ModelInfo struct {
	ID                  string   `json:"id"`
	Provider            string   `json:"provider"`
	DisplayName         string   `json:"display_name"`
	ContextWindow       int      `json:"context_window"`
	MaxOutput           *int     `json:"max_output,omitempty"`
	SupportsTools       bool     `json:"supports_tools"`
	SupportsVision      bool     `json:"supports_vision"`
	SupportsReasoning   bool     `json:"supports_reasoning"`
	InputCostPerMillion  *float64 `json:"input_cost_per_million,omitempty"`
	OutputCostPerMillion *float64 `json:"output_cost_per_million,omitempty"`
	Aliases             []string `json:"aliases,omitempty"`
}

func intPtr(v int) *int       { return &v }
func floatPtr(v float64) *float64 { return &v }

// Models is the built-in model catalog (February 2026).
var Models = []ModelInfo{
	// Anthropic
	{
		ID: "claude-opus-4-6", Provider: "anthropic", DisplayName: "Claude Opus 4.6",
		ContextWindow: 200000, MaxOutput: intPtr(32768),
		SupportsTools: true, SupportsVision: true, SupportsReasoning: true,
		InputCostPerMillion: floatPtr(15.0), OutputCostPerMillion: floatPtr(75.0),
		Aliases: []string{"opus", "claude-opus"},
	},
	{
		ID: "claude-sonnet-4-5", Provider: "anthropic", DisplayName: "Claude Sonnet 4.5",
		ContextWindow: 200000, MaxOutput: intPtr(16384),
		SupportsTools: true, SupportsVision: true, SupportsReasoning: true,
		InputCostPerMillion: floatPtr(3.0), OutputCostPerMillion: floatPtr(15.0),
		Aliases: []string{"sonnet", "claude-sonnet"},
	},

	// OpenAI
	{
		ID: "gpt-5.2", Provider: "openai", DisplayName: "GPT-5.2",
		ContextWindow: 1047576, MaxOutput: intPtr(32768),
		SupportsTools: true, SupportsVision: true, SupportsReasoning: true,
		InputCostPerMillion: floatPtr(2.50), OutputCostPerMillion: floatPtr(10.0),
		Aliases: []string{"gpt5"},
	},
	{
		ID: "gpt-5.2-mini", Provider: "openai", DisplayName: "GPT-5.2 Mini",
		ContextWindow: 1047576, MaxOutput: intPtr(16384),
		SupportsTools: true, SupportsVision: true, SupportsReasoning: true,
		InputCostPerMillion: floatPtr(0.75), OutputCostPerMillion: floatPtr(3.0),
		Aliases: []string{"gpt5-mini"},
	},
	{
		ID: "gpt-5.2-codex", Provider: "openai", DisplayName: "GPT-5.2 Codex",
		ContextWindow: 1047576, MaxOutput: intPtr(32768),
		SupportsTools: true, SupportsVision: true, SupportsReasoning: true,
		InputCostPerMillion: floatPtr(2.50), OutputCostPerMillion: floatPtr(10.0),
		Aliases: []string{"codex"},
	},

	// Gemini
	{
		ID: "gemini-3-pro-preview", Provider: "gemini", DisplayName: "Gemini 3 Pro (Preview)",
		ContextWindow: 1048576, MaxOutput: intPtr(65536),
		SupportsTools: true, SupportsVision: true, SupportsReasoning: true,
		InputCostPerMillion: floatPtr(1.25), OutputCostPerMillion: floatPtr(5.0),
		Aliases: []string{"gemini-pro", "gemini-3-pro"},
	},
	{
		ID: "gemini-3-flash-preview", Provider: "gemini", DisplayName: "Gemini 3 Flash (Preview)",
		ContextWindow: 1048576, MaxOutput: intPtr(65536),
		SupportsTools: true, SupportsVision: true, SupportsReasoning: true,
		InputCostPerMillion: floatPtr(0.15), OutputCostPerMillion: floatPtr(0.60),
		Aliases: []string{"gemini-flash", "gemini-3-flash"},
	},
}

// GetModelInfo returns the catalog entry for a model, or nil if unknown.
func GetModelInfo(modelID string) *ModelInfo {
	for i := range Models {
		if Models[i].ID == modelID {
			return &Models[i]
		}
		for _, alias := range Models[i].Aliases {
			if alias == modelID {
				return &Models[i]
			}
		}
	}
	return nil
}

// ListModels returns all known models, optionally filtered by provider.
func ListModels(provider string) []ModelInfo {
	if provider == "" {
		result := make([]ModelInfo, len(Models))
		copy(result, Models)
		return result
	}
	var result []ModelInfo
	for _, m := range Models {
		if m.Provider == provider {
			result = append(result, m)
		}
	}
	return result
}

// GetLatestModel returns the first (newest/best) model for a provider,
// optionally filtered by capability.
func GetLatestModel(provider string, capability string) *ModelInfo {
	for i := range Models {
		if Models[i].Provider != provider {
			continue
		}
		switch capability {
		case "":
			return &Models[i]
		case "vision":
			if Models[i].SupportsVision {
				return &Models[i]
			}
		case "tools":
			if Models[i].SupportsTools {
				return &Models[i]
			}
		case "reasoning":
			if Models[i].SupportsReasoning {
				return &Models[i]
			}
		}
	}
	return nil
}
