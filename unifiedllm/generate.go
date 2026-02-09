package unifiedllm

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
)

// GenerateOptions configures a high-level generate() call.
type GenerateOptions struct {
	Model           string
	Prompt          string     // simple text prompt (mutually exclusive with Messages)
	Messages        []Message  // full conversation (mutually exclusive with Prompt)
	System          string
	Tools           []Tool
	ToolChoice      *ToolChoice
	MaxToolRounds   int // default 1
	StopWhen        StopCondition
	ResponseFormat  *ResponseFormat
	Temperature     *float64
	TopP            *float64
	MaxTokens       *int
	StopSequences   []string
	ReasoningEffort string
	Provider        string
	ProviderOptions map[string]interface{}
	MaxRetries      int // default 2
	Timeout         *TimeoutConfig
	Client          *Client
}

// Generate is the high-level blocking generation function.
// It wraps Client.Complete with tool execution loops, automatic retries,
// and prompt standardization.
func Generate(ctx context.Context, opts GenerateOptions) (*GenerateResult, error) {
	// Validate mutually exclusive options.
	if opts.Prompt != "" && len(opts.Messages) > 0 {
		return nil, &ConfigurationError{SDKError: SDKError{
			Message: "cannot specify both prompt and messages",
		}}
	}

	client := opts.Client
	if client == nil {
		client = GetDefaultClient()
	}

	if opts.MaxToolRounds == 0 && len(opts.Tools) > 0 {
		opts.MaxToolRounds = 1
	}

	retryPolicy := DefaultRetryPolicy()
	if opts.MaxRetries > 0 {
		retryPolicy.MaxRetries = opts.MaxRetries
	} else if opts.MaxRetries == 0 && len(opts.Tools) == 0 {
		// Default to 2 retries for simple calls.
		retryPolicy.MaxRetries = 2
	}

	// Build initial messages.
	messages := opts.Messages
	if opts.Prompt != "" {
		messages = []Message{UserMessage(opts.Prompt)}
	}
	if opts.System != "" {
		messages = append([]Message{SystemMessage(opts.System)}, messages...)
	}

	// Build tool definitions.
	var toolDefs []ToolDefinition
	toolMap := make(map[string]Tool)
	hasActiveTools := false
	for _, t := range opts.Tools {
		toolDefs = append(toolDefs, ToolDefinition{
			Name:        t.Name,
			Description: t.Description,
			Parameters:  t.Parameters,
		})
		toolMap[t.Name] = t
		if t.Execute != nil {
			hasActiveTools = true
		}
	}

	// Tool execution loop.
	var steps []StepResult
	var totalUsage Usage
	conversation := make([]Message, len(messages))
	copy(conversation, messages)

	for round := 0; round <= opts.MaxToolRounds; round++ {
		req := Request{
			Model:           opts.Model,
			Messages:        conversation,
			Provider:        opts.Provider,
			Tools:           opts.Tools,
			ToolDefs:        toolDefs,
			ToolChoice:      opts.ToolChoice,
			ResponseFormat:  opts.ResponseFormat,
			Temperature:     opts.Temperature,
			TopP:            opts.TopP,
			MaxTokens:       opts.MaxTokens,
			StopSequences:   opts.StopSequences,
			ReasoningEffort: opts.ReasoningEffort,
			ProviderOptions: opts.ProviderOptions,
		}

		// Call with retry.
		resp, err := Retry(ctx, retryPolicy, func(ctx context.Context) (*Response, error) {
			return client.Complete(ctx, req)
		})
		if err != nil {
			return nil, err
		}

		// Extract tool calls.
		toolCalls := resp.ToolCallsFromResponse()

		// Execute active tools if present.
		var toolResults []ToolResult
		if len(toolCalls) > 0 && resp.FinishReason.Reason == "tool_calls" && hasActiveTools {
			toolResults = executeToolsConcurrently(toolMap, toolCalls)
		}

		step := StepResult{
			Text:         resp.Text(),
			Reasoning:    resp.Reasoning(),
			ToolCalls:    toolCalls,
			ToolResults:  toolResults,
			FinishReason: resp.FinishReason,
			Usage:        resp.Usage,
			Response:     *resp,
			Warnings:     resp.Warnings,
		}
		steps = append(steps, step)
		totalUsage = totalUsage.Add(resp.Usage)

		// Check stop conditions.
		if len(toolCalls) == 0 || resp.FinishReason.Reason != "tool_calls" {
			break // Natural completion.
		}
		if !hasActiveTools {
			break // Passive tools; return to caller.
		}
		if round >= opts.MaxToolRounds {
			break // Budget exhausted.
		}
		if opts.StopWhen != nil && opts.StopWhen(steps) {
			break // Custom stop condition.
		}

		// Append assistant message with tool calls and tool results.
		conversation = append(conversation, resp.Message)
		for _, result := range toolResults {
			contentBytes, _ := json.Marshal(result.Content)
			conversation = append(conversation, ToolResultMessage(
				result.ToolCallID,
				string(contentBytes),
				result.IsError,
			))
		}
	}

	lastStep := steps[len(steps)-1]
	return &GenerateResult{
		Text:         lastStep.Text,
		Reasoning:    lastStep.Reasoning,
		ToolCalls:    lastStep.ToolCalls,
		ToolResults:  lastStep.ToolResults,
		FinishReason: lastStep.FinishReason,
		Usage:        lastStep.Usage,
		TotalUsage:   totalUsage,
		Steps:        steps,
		Response:     lastStep.Response,
	}, nil
}

// executeToolsConcurrently executes all tool calls in parallel.
func executeToolsConcurrently(toolMap map[string]Tool, calls []ToolCall) []ToolResult {
	results := make([]ToolResult, len(calls))
	var wg sync.WaitGroup

	for i, call := range calls {
		wg.Add(1)
		go func(idx int, tc ToolCall) {
			defer wg.Done()

			tool, ok := toolMap[tc.Name]
			if !ok || tool.Execute == nil {
				results[idx] = ToolResult{
					ToolCallID: tc.ID,
					Content:    fmt.Sprintf("Unknown tool: %s", tc.Name),
					IsError:    true,
				}
				return
			}

			output, err := tool.Execute(tc.Arguments)
			if err != nil {
				results[idx] = ToolResult{
					ToolCallID: tc.ID,
					Content:    fmt.Sprintf("Tool execution error: %v", err),
					IsError:    true,
				}
				return
			}

			results[idx] = ToolResult{
				ToolCallID: tc.ID,
				Content:    output,
				IsError:    false,
			}
		}(i, call)
	}

	wg.Wait()
	return results
}

// StreamResult wraps a streaming response with convenience accessors.
type StreamResult struct {
	events   <-chan StreamEvent
	response *Response
	mu       sync.Mutex
	done     bool
}

// Events returns the channel of stream events.
func (sr *StreamResult) Events() <-chan StreamEvent {
	return sr.events
}

// Response returns the accumulated response after the stream ends.
// Returns nil if the stream has not finished yet.
func (sr *StreamResult) Response() *Response {
	sr.mu.Lock()
	defer sr.mu.Unlock()
	return sr.response
}

// StreamGenerate is the high-level streaming generation function.
func StreamGenerate(ctx context.Context, opts GenerateOptions) (*StreamResult, error) {
	if opts.Prompt != "" && len(opts.Messages) > 0 {
		return nil, &ConfigurationError{SDKError: SDKError{
			Message: "cannot specify both prompt and messages",
		}}
	}

	client := opts.Client
	if client == nil {
		client = GetDefaultClient()
	}

	messages := opts.Messages
	if opts.Prompt != "" {
		messages = []Message{UserMessage(opts.Prompt)}
	}
	if opts.System != "" {
		messages = append([]Message{SystemMessage(opts.System)}, messages...)
	}

	var toolDefs []ToolDefinition
	for _, t := range opts.Tools {
		toolDefs = append(toolDefs, ToolDefinition{
			Name:        t.Name,
			Description: t.Description,
			Parameters:  t.Parameters,
		})
	}

	req := Request{
		Model:           opts.Model,
		Messages:        messages,
		Provider:        opts.Provider,
		Tools:           opts.Tools,
		ToolDefs:        toolDefs,
		ToolChoice:      opts.ToolChoice,
		ResponseFormat:  opts.ResponseFormat,
		Temperature:     opts.Temperature,
		TopP:            opts.TopP,
		MaxTokens:       opts.MaxTokens,
		StopSequences:   opts.StopSequences,
		ReasoningEffort: opts.ReasoningEffort,
		ProviderOptions: opts.ProviderOptions,
	}

	eventCh, err := client.Stream(ctx, req)
	if err != nil {
		return nil, err
	}

	// Wrap the event channel to capture the final response.
	outCh := make(chan StreamEvent, 64)
	sr := &StreamResult{events: outCh}

	go func() {
		defer close(outCh)
		for event := range eventCh {
			outCh <- event
			if event.Type == StreamFinish && event.Response != nil {
				sr.mu.Lock()
				sr.response = event.Response
				sr.done = true
				sr.mu.Unlock()
			}
		}
	}()

	return sr, nil
}

// GenerateObject generates structured output with schema validation.
func GenerateObject(ctx context.Context, opts GenerateOptions, schema map[string]interface{}) (*GenerateResult, error) {
	opts.ResponseFormat = &ResponseFormat{
		Type:       "json_schema",
		JSONSchema: schema,
		Strict:     true,
	}

	// Add schema instructions to the system prompt for providers that don't
	// support native structured output (like Anthropic).
	schemaJSON, _ := json.MarshalIndent(schema, "", "  ")
	schemaInstruction := fmt.Sprintf(
		"\nYou must respond with valid JSON matching this schema:\n```json\n%s\n```\nRespond ONLY with the JSON object, no other text.",
		string(schemaJSON),
	)

	if opts.System != "" {
		opts.System += schemaInstruction
	} else {
		opts.System = schemaInstruction
	}

	result, err := Generate(ctx, opts)
	if err != nil {
		return nil, err
	}

	// Parse the output.
	var output interface{}
	text := result.Text
	if err := json.Unmarshal([]byte(text), &output); err != nil {
		return nil, &NoObjectGeneratedError{SDKError: SDKError{
			Message: fmt.Sprintf("failed to parse structured output: %v", err),
			Cause:   err,
		}}
	}

	result.Output = output
	return result, nil
}

// StreamAccumulator collects stream events into a complete Response.
type StreamAccumulator struct {
	textParts      map[string]string
	reasoningParts []string
	toolCalls      []ToolCall
	finishReason   *FinishReason
	usage          *Usage
	response       *Response
}

// NewStreamAccumulator creates a new StreamAccumulator.
func NewStreamAccumulator() *StreamAccumulator {
	return &StreamAccumulator{
		textParts: make(map[string]string),
	}
}

// Process ingests a single stream event.
func (sa *StreamAccumulator) Process(event StreamEvent) {
	switch event.Type {
	case TextDelta:
		id := event.TextID
		if id == "" {
			id = "default"
		}
		sa.textParts[id] += event.Delta
	case ReasoningDelta:
		sa.reasoningParts = append(sa.reasoningParts, event.ReasoningDelta)
	case ToolCallEnd:
		if event.ToolCall != nil {
			sa.toolCalls = append(sa.toolCalls, *event.ToolCall)
		}
	case StreamFinish:
		sa.finishReason = event.FinishReason
		sa.usage = event.Usage
		sa.response = event.Response
	}
}

// Response returns the accumulated response.
func (sa *StreamAccumulator) Response() *Response {
	if sa.response != nil {
		return sa.response
	}
	// Build a response from accumulated parts.
	var content []ContentPart
	for _, text := range sa.textParts {
		content = append(content, TextPart(text))
	}
	for _, tc := range sa.toolCalls {
		content = append(content, ToolCallPart(tc.ID, tc.Name, tc.Arguments))
	}

	fr := FinishReason{Reason: "stop"}
	if sa.finishReason != nil {
		fr = *sa.finishReason
	}

	usage := Usage{}
	if sa.usage != nil {
		usage = *sa.usage
	}

	return &Response{
		Message:      Message{Role: RoleAssistant, Content: content},
		FinishReason: fr,
		Usage:        usage,
	}
}
