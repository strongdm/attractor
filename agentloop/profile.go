package agentloop

// ProviderProfile defines the provider-aligned tool and prompt configuration.
// Each profile corresponds to a model family and mirrors the provider's native
// agent toolset and system prompt.
type ProviderProfile interface {
	// ID returns the provider identifier (e.g., "openai", "anthropic", "gemini").
	ID() string

	// Model returns the model identifier (e.g., "claude-opus-4-6").
	ModelID() string

	// ToolRegistry returns the tool registry for this profile.
	ToolRegistry() *ToolRegistry

	// BuildSystemPrompt constructs the full system prompt from environment
	// context and project documentation.
	BuildSystemPrompt(env ExecutionEnvironment, projectDocs string) string

	// Tools returns tool definitions for the LLM request.
	Tools() []ToolDefinition

	// ProviderOptions returns provider-specific request options.
	ProviderOptions() map[string]interface{}

	// Capability flags.
	SupportsReasoning() bool
	SupportsStreaming() bool
	SupportsParallelToolCalls() bool
	ContextWindowSize() int
}

// BaseProfile provides common profile fields and default implementations.
type BaseProfile struct {
	providerID                string
	model                     string
	registry                  *ToolRegistry
	supportsReasoning         bool
	supportsStreaming          bool
	supportsParallelToolCalls bool
	contextWindowSize         int
}

func (p *BaseProfile) ID() string           { return p.providerID }
func (p *BaseProfile) ModelID() string       { return p.model }
func (p *BaseProfile) ToolRegistry() *ToolRegistry { return p.registry }

func (p *BaseProfile) Tools() []ToolDefinition {
	return p.registry.Definitions()
}

func (p *BaseProfile) ProviderOptions() map[string]interface{} {
	return nil
}

func (p *BaseProfile) SupportsReasoning() bool         { return p.supportsReasoning }
func (p *BaseProfile) SupportsStreaming() bool          { return p.supportsStreaming }
func (p *BaseProfile) SupportsParallelToolCalls() bool  { return p.supportsParallelToolCalls }
func (p *BaseProfile) ContextWindowSize() int           { return p.contextWindowSize }
