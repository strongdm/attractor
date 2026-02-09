// Package unifiedllm provides a unified LLM client SDK that wraps the gollm
// library (github.com/teilomillet/gollm) to present a provider-agnostic
// interface conforming to the unified-llm-spec.
//
// # Architecture
//
// The package follows a four-layer architecture:
//
//   - Layer 1 (Provider Specification): ProviderAdapter interface and shared types
//   - Layer 2 (Provider Utilities): Retry logic, error classification helpers
//   - Layer 3 (Core Client): Client with provider routing and middleware
//   - Layer 4 (High-Level API): Generate, StreamGenerate, GenerateObject functions
//
// # Quick Start
//
// Using the high-level API with environment-based configuration:
//
//	result, err := unifiedllm.Generate(ctx, unifiedllm.GenerateOptions{
//	    Model:  "claude-opus-4-6",
//	    Prompt: "Explain quantum computing in one paragraph",
//	})
//	fmt.Println(result.Text)
//
// Using the Client directly:
//
//	adapter, _ := unifiedllm.NewGollmAdapter("openai", os.Getenv("OPENAI_API_KEY"))
//	client := unifiedllm.NewClient(unifiedllm.WithProvider("openai", adapter))
//
//	resp, _ := client.Complete(ctx, unifiedllm.Request{
//	    Model:    "gpt-5.2",
//	    Messages: []unifiedllm.Message{unifiedllm.UserMessage("Hello")},
//	})
//	fmt.Println(resp.Text())
//
// # GollmAdapter
//
// The GollmAdapter wraps gollm.LLM to implement the ProviderAdapter interface.
// It translates between the unified spec types and gollm's native API, supporting
// OpenAI, Anthropic, and other providers that gollm supports.
//
// # Tool Calling
//
// Tools can be defined with optional Execute handlers for automatic tool loops:
//
//	tool := unifiedllm.Tool{
//	    Name:        "get_weather",
//	    Description: "Get the current weather for a location",
//	    Parameters: map[string]interface{}{
//	        "type": "object",
//	        "properties": map[string]interface{}{
//	            "city": map[string]interface{}{"type": "string"},
//	        },
//	    },
//	    Execute: func(args json.RawMessage) (interface{}, error) {
//	        return "72F and sunny", nil
//	    },
//	}
//
// # Model Catalog
//
// A built-in catalog of known models helps select valid model identifiers:
//
//	info := unifiedllm.GetModelInfo("claude-opus-4-6")
//	models := unifiedllm.ListModels("anthropic")
//	latest := unifiedllm.GetLatestModel("openai", "reasoning")
package unifiedllm
