package unifiedllm

import "context"

// ProviderAdapter is the interface every provider backend must implement.
// This matches the spec's ProviderAdapter contract (Section 2.4, 7.1).
type ProviderAdapter interface {
	// Name returns the provider identifier (e.g. "openai", "anthropic", "gemini").
	Name() string

	// Complete sends a blocking request and returns the full response.
	Complete(ctx context.Context, req Request) (*Response, error)

	// Stream sends a request and returns a channel of stream events.
	Stream(ctx context.Context, req Request) (<-chan StreamEvent, error)
}

// OptionalAdapter methods that adapters may implement.

// Closer is implemented by adapters that hold resources.
type Closer interface {
	Close() error
}

// Initializer is implemented by adapters that need startup validation.
type Initializer interface {
	Initialize() error
}

// ToolChoiceSupporter is implemented by adapters that can report tool choice support.
type ToolChoiceSupporter interface {
	SupportsToolChoice(mode string) bool
}
