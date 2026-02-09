package unifiedllm

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"strings"

	"github.com/google/uuid"
	"github.com/teilomillet/gollm"
)

// GollmAdapter wraps a gollm.LLM instance and implements ProviderAdapter.
// It translates between the unified spec types and gollm's API.
type GollmAdapter struct {
	provider string
	llm      gollm.LLM
	model    string
}

// GollmAdapterOption configures a GollmAdapter.
type GollmAdapterOption func(*gollmAdapterConfig)

type gollmAdapterConfig struct {
	apiKey      string
	model       string
	maxTokens   int
	temperature float64
	extraOpts   []gollm.ConfigOption
}

// WithAPIKey sets the API key for the adapter.
func WithAPIKey(key string) GollmAdapterOption {
	return func(c *gollmAdapterConfig) {
		c.apiKey = key
	}
}

// WithModel sets the default model for the adapter.
func WithModel(model string) GollmAdapterOption {
	return func(c *gollmAdapterConfig) {
		c.model = model
	}
}

// WithMaxTokens sets the default max tokens.
func WithMaxTokens(n int) GollmAdapterOption {
	return func(c *gollmAdapterConfig) {
		c.maxTokens = n
	}
}

// WithTemperature sets the default temperature.
func WithTemperature(t float64) GollmAdapterOption {
	return func(c *gollmAdapterConfig) {
		c.temperature = t
	}
}

// WithGollmOptions adds extra gollm configuration options.
func WithGollmOptions(opts ...gollm.ConfigOption) GollmAdapterOption {
	return func(c *gollmAdapterConfig) {
		c.extraOpts = append(c.extraOpts, opts...)
	}
}

// NewGollmAdapter creates a new GollmAdapter for the given provider.
// If apiKey is empty, gollm will attempt to read it from environment variables.
func NewGollmAdapter(provider string, apiKey string, opts ...GollmAdapterOption) (*GollmAdapter, error) {
	cfg := &gollmAdapterConfig{
		apiKey:      apiKey,
		maxTokens:   4096,
		temperature: 0.7,
	}
	for _, opt := range opts {
		opt(cfg)
	}

	// Determine default model for provider.
	model := cfg.model
	if model == "" {
		if info := GetLatestModel(provider, ""); info != nil {
			model = info.ID
		} else {
			// Fallback defaults.
			switch provider {
			case "openai":
				model = "gpt-4o-mini"
			case "anthropic":
				model = "claude-sonnet-4-5-20250514"
			default:
				model = "gpt-4o-mini"
			}
		}
	}

	gollmOpts := []gollm.ConfigOption{
		gollm.SetProvider(provider),
		gollm.SetModel(model),
		gollm.SetMaxTokens(cfg.maxTokens),
		gollm.SetTemperature(cfg.temperature),
		gollm.SetMaxRetries(0), // We handle retries ourselves.
		gollm.SetLogLevel(gollm.LogLevelWarn),
	}

	if cfg.apiKey != "" {
		gollmOpts = append(gollmOpts, gollm.SetAPIKey(cfg.apiKey))
	}

	gollmOpts = append(gollmOpts, cfg.extraOpts...)

	llm, err := gollm.NewLLM(gollmOpts...)
	if err != nil {
		return nil, fmt.Errorf("failed to create gollm LLM for provider %s: %w", provider, err)
	}

	return &GollmAdapter{
		provider: provider,
		llm:      llm,
		model:    model,
	}, nil
}

// NewGollmAdapterFromLLM wraps an existing gollm.LLM instance.
func NewGollmAdapterFromLLM(provider string, llm gollm.LLM) *GollmAdapter {
	return &GollmAdapter{
		provider: provider,
		llm:      llm,
	}
}

// Name returns the provider identifier.
func (a *GollmAdapter) Name() string {
	return a.provider
}

// Complete sends a blocking request and returns the full response.
func (a *GollmAdapter) Complete(ctx context.Context, req Request) (*Response, error) {
	prompt, err := a.translateRequest(req)
	if err != nil {
		return nil, err
	}

	// Apply request-level overrides via gollm SetOption.
	a.applyRequestOptions(req)

	text, err := a.llm.Generate(ctx, prompt)
	if err != nil {
		return nil, a.translateError(err)
	}

	return a.buildResponse(req, text), nil
}

// Stream sends a streaming request and returns a channel of StreamEvent objects.
func (a *GollmAdapter) Stream(ctx context.Context, req Request) (<-chan StreamEvent, error) {
	prompt, err := a.translateRequest(req)
	if err != nil {
		return nil, err
	}

	a.applyRequestOptions(req)

	ch := make(chan StreamEvent, 64)

	if !a.llm.SupportsStreaming() {
		// Fallback: generate full response and emit as single delta.
		go func() {
			defer close(ch)
			ch <- StreamEvent{Type: StreamStart}

			text, err := a.llm.Generate(ctx, prompt)
			if err != nil {
				ch <- StreamEvent{Type: StreamError, Error: a.translateError(err)}
				return
			}

			textID := "text_0"
			ch <- StreamEvent{Type: TextStart, TextID: textID}
			ch <- StreamEvent{Type: TextDelta, Delta: text, TextID: textID}
			ch <- StreamEvent{Type: TextEnd, TextID: textID}

			resp := a.buildResponse(req, text)
			ch <- StreamEvent{
				Type:         StreamFinish,
				FinishReason: &resp.FinishReason,
				Usage:        &resp.Usage,
				Response:     resp,
			}
		}()
		return ch, nil
	}

	// Use gollm streaming.
	stream, err := a.llm.Stream(ctx, prompt)
	if err != nil {
		return nil, a.translateError(err)
	}

	go func() {
		defer close(ch)
		defer stream.Close()

		ch <- StreamEvent{Type: StreamStart}

		textID := "text_0"
		started := false
		var fullText strings.Builder

		for {
			token, err := stream.Next(ctx)
			if err == io.EOF {
				break
			}
			if err != nil {
				ch <- StreamEvent{Type: StreamError, Error: a.translateError(err)}
				return
			}
			if token == nil {
				continue
			}

			if !started {
				ch <- StreamEvent{Type: TextStart, TextID: textID}
				started = true
			}

			ch <- StreamEvent{Type: TextDelta, Delta: token.Text, TextID: textID}
			fullText.WriteString(token.Text)
		}

		if started {
			ch <- StreamEvent{Type: TextEnd, TextID: textID}
		}

		resp := a.buildResponse(req, fullText.String())
		ch <- StreamEvent{
			Type:         StreamFinish,
			FinishReason: &resp.FinishReason,
			Usage:        &resp.Usage,
			Response:     resp,
		}
	}()

	return ch, nil
}

// SupportsToolChoice reports whether the adapter supports a particular tool choice mode.
func (a *GollmAdapter) SupportsToolChoice(mode string) bool {
	switch mode {
	case "auto", "none", "required":
		return true
	case "named":
		return a.provider != "gemini" // Gemini has limited named tool support
	default:
		return false
	}
}

// translateRequest converts a unified Request into a gollm Prompt.
func (a *GollmAdapter) translateRequest(req Request) (*gollm.Prompt, error) {
	// Build the prompt from messages.
	var systemPrompt string
	var userParts []string

	for _, msg := range req.Messages {
		switch msg.Role {
		case RoleSystem, RoleDeveloper:
			systemPrompt += msg.TextContent() + "\n"
		case RoleUser:
			userParts = append(userParts, msg.TextContent())
		case RoleAssistant:
			// For multi-turn, include assistant context.
			text := msg.TextContent()
			if text != "" {
				userParts = append(userParts, "[Assistant]: "+text)
			}
		case RoleTool:
			// Include tool results as context.
			for _, part := range msg.Content {
				if part.Kind == ContentToolResult && part.ToolResult != nil {
					var content string
					_ = json.Unmarshal(part.ToolResult.Content, &content)
					if content == "" {
						content = string(part.ToolResult.Content)
					}
					prefix := "[Tool Result]"
					if part.ToolResult.IsError {
						prefix = "[Tool Error]"
					}
					userParts = append(userParts, prefix+": "+content)
				}
			}
		}
	}

	// Combine user messages into a single prompt for gollm.
	promptText := strings.Join(userParts, "\n")
	if promptText == "" {
		promptText = "Hello"
	}

	promptOpts := []gollm.PromptOption{}

	if systemPrompt != "" {
		promptOpts = append(promptOpts, gollm.WithSystemPrompt(strings.TrimSpace(systemPrompt), gollm.CacheTypeEphemeral))
	}

	if req.MaxTokens != nil {
		promptOpts = append(promptOpts, gollm.WithMaxLength(*req.MaxTokens))
	}

	// Add tool definitions if present.
	if len(req.Tools) > 0 {
		tools := make([]gollm.Tool, 0, len(req.Tools))
		for _, t := range req.Tools {
			paramBytes, _ := json.Marshal(t.Parameters)
			var params map[string]interface{}
			_ = json.Unmarshal(paramBytes, &params)

			tools = append(tools, gollm.Tool{
				Type: "function",
				Function: gollm.Function{
					Name:        t.Name,
					Description: t.Description,
					Parameters:  params,
				},
			})
		}
		promptOpts = append(promptOpts, gollm.WithTools(tools))
	}

	// Also check ToolDefs.
	if len(req.ToolDefs) > 0 {
		tools := make([]gollm.Tool, 0, len(req.ToolDefs))
		for _, t := range req.ToolDefs {
			tools = append(tools, gollm.Tool{
				Type: "function",
				Function: gollm.Function{
					Name:        t.Name,
					Description: t.Description,
					Parameters:  t.Parameters,
				},
			})
		}
		promptOpts = append(promptOpts, gollm.WithTools(tools))
	}

	// Map tool choice.
	if req.ToolChoice != nil {
		promptOpts = append(promptOpts, gollm.WithToolChoice(req.ToolChoice.Mode))
	}

	prompt := gollm.NewPrompt(promptText, promptOpts...)
	return prompt, nil
}

// applyRequestOptions applies request-level parameters to the gollm LLM.
func (a *GollmAdapter) applyRequestOptions(req Request) {
	if req.Model != "" {
		a.llm.SetOption("model", req.Model)
	}
	if req.Temperature != nil {
		a.llm.SetOption("temperature", *req.Temperature)
	}
	if req.TopP != nil {
		a.llm.SetOption("top_p", *req.TopP)
	}
	if req.MaxTokens != nil {
		a.llm.SetOption("max_tokens", *req.MaxTokens)
	}
}

// buildResponse constructs a unified Response from the generated text.
func (a *GollmAdapter) buildResponse(req Request, text string) *Response {
	model := req.Model
	if model == "" {
		model = a.model
	}

	// Attempt to parse tool calls from the response text.
	var contentParts []ContentPart
	toolCalls := a.parseToolCalls(text)

	if len(toolCalls) > 0 {
		for _, tc := range toolCalls {
			contentParts = append(contentParts, ContentPart{
				Kind:     ContentToolCall,
				ToolCall: &tc,
			})
		}
	}

	// Always include any remaining text.
	cleanedText := a.removeToolCallJSON(text, toolCalls)
	if cleanedText != "" {
		contentParts = append([]ContentPart{TextPart(cleanedText)}, contentParts...)
	}

	if len(contentParts) == 0 {
		contentParts = []ContentPart{TextPart(text)}
	}

	finishReason := FinishReason{Reason: "stop", Raw: "stop"}
	if len(toolCalls) > 0 {
		finishReason = FinishReason{Reason: "tool_calls", Raw: "tool_calls"}
	}

	return &Response{
		ID:       "resp_" + uuid.New().String()[:8],
		Model:    model,
		Provider: a.provider,
		Message: Message{
			Role:    RoleAssistant,
			Content: contentParts,
		},
		FinishReason: finishReason,
		Usage: Usage{
			// gollm doesn't expose detailed usage; estimate from text length.
			// Real usage would come from the provider's response headers.
			InputTokens:  estimateTokens(req),
			OutputTokens: len(text) / 4, // rough approximation
			TotalTokens:  estimateTokens(req) + len(text)/4,
		},
	}
}

// parseToolCalls attempts to extract tool calls from the response text.
// gollm may return tool calls as JSON in the response text.
func (a *GollmAdapter) parseToolCalls(text string) []ToolCallData {
	// Try to detect structured tool call patterns in the text.
	// This handles cases where gollm returns tool calls embedded in text.
	var calls []ToolCallData

	// Look for JSON objects that look like function calls.
	// Common patterns: {"name": "...", "arguments": {...}} or similar.
	start := strings.Index(text, `{"tool_calls"`)
	if start == -1 {
		start = strings.Index(text, `[{"name"`)
	}
	if start == -1 {
		return nil
	}

	// Try to parse as a tool calls array.
	var rawCalls []struct {
		Name      string          `json:"name"`
		Arguments json.RawMessage `json:"arguments"`
	}

	remaining := text[start:]
	if err := json.Unmarshal([]byte(remaining), &rawCalls); err == nil {
		for _, rc := range rawCalls {
			calls = append(calls, ToolCallData{
				ID:        "call_" + uuid.New().String()[:8],
				Name:      rc.Name,
				Arguments: rc.Arguments,
				Type:      "function",
			})
		}
	}

	return calls
}

// removeToolCallJSON removes parsed tool call JSON from the text.
func (a *GollmAdapter) removeToolCallJSON(text string, calls []ToolCallData) string {
	if len(calls) == 0 {
		return text
	}
	// Simple cleanup: remove JSON blocks that were parsed as tool calls.
	result := text
	for _, patterns := range []string{`{"tool_calls"`, `[{"name"`} {
		if idx := strings.Index(result, patterns); idx != -1 {
			result = strings.TrimSpace(result[:idx])
		}
	}
	return result
}

// translateError converts a gollm error into the unified error hierarchy.
func (a *GollmAdapter) translateError(err error) error {
	if err == nil {
		return nil
	}
	msg := err.Error()

	// Classify based on error message content.
	msgLower := strings.ToLower(msg)
	switch {
	case strings.Contains(msgLower, "401") || strings.Contains(msgLower, "unauthorized") || strings.Contains(msgLower, "invalid key") || strings.Contains(msgLower, "invalid api key"):
		return &AuthenticationError{ProviderError: ProviderError{
			SDKError: SDKError{Message: msg, Cause: err}, Provider: a.provider, StatusCode: 401,
		}}
	case strings.Contains(msgLower, "403") || strings.Contains(msgLower, "forbidden"):
		return &AccessDeniedError{ProviderError: ProviderError{
			SDKError: SDKError{Message: msg, Cause: err}, Provider: a.provider, StatusCode: 403,
		}}
	case strings.Contains(msgLower, "404") || strings.Contains(msgLower, "not found"):
		return &NotFoundError{ProviderError: ProviderError{
			SDKError: SDKError{Message: msg, Cause: err}, Provider: a.provider, StatusCode: 404,
		}}
	case strings.Contains(msgLower, "429") || strings.Contains(msgLower, "rate limit"):
		return &RateLimitError{ProviderError: ProviderError{
			SDKError: SDKError{Message: msg, Cause: err}, Provider: a.provider, StatusCode: 429, Retryable: true,
		}}
	case strings.Contains(msgLower, "context length") || strings.Contains(msgLower, "too many tokens"):
		return &ContextLengthError{ProviderError: ProviderError{
			SDKError: SDKError{Message: msg, Cause: err}, Provider: a.provider, StatusCode: 413,
		}}
	case strings.Contains(msgLower, "500") || strings.Contains(msgLower, "internal server"):
		return &ServerError{ProviderError: ProviderError{
			SDKError: SDKError{Message: msg, Cause: err}, Provider: a.provider, StatusCode: 500, Retryable: true,
		}}
	case strings.Contains(msgLower, "timeout"):
		return &RequestTimeoutError{SDKError: SDKError{Message: msg, Cause: err}}
	case strings.Contains(msgLower, "content filter") || strings.Contains(msgLower, "safety"):
		return &ContentFilterError{ProviderError: ProviderError{
			SDKError: SDKError{Message: msg, Cause: err}, Provider: a.provider,
		}}
	default:
		// Wrap as a generic provider error (retryable by default).
		return &ProviderError{
			SDKError:  SDKError{Message: msg, Cause: err},
			Provider:  a.provider,
			Retryable: true,
		}
	}
}

// estimateTokens provides a rough token count estimate from request messages.
func estimateTokens(req Request) int {
	total := 0
	for _, msg := range req.Messages {
		for _, part := range msg.Content {
			if part.Kind == ContentText {
				total += len(part.Text) / 4
			}
		}
	}
	if total == 0 {
		total = 10
	}
	return total
}
