// Package unifiedllm provides a unified LLM client SDK that wraps gollm to
// present a provider-agnostic interface conforming to the unified-llm-spec.
package unifiedllm

import (
	"encoding/json"
	"strings"
	"time"
)

// Role identifies who produced a message in a conversation.
type Role string

const (
	RoleSystem    Role = "system"
	RoleUser      Role = "user"
	RoleAssistant Role = "assistant"
	RoleTool      Role = "tool"
	RoleDeveloper Role = "developer"
)

// ContentKind is the discriminator tag for ContentPart.
type ContentKind string

const (
	ContentText             ContentKind = "text"
	ContentImage            ContentKind = "image"
	ContentAudio            ContentKind = "audio"
	ContentDocument         ContentKind = "document"
	ContentToolCall         ContentKind = "tool_call"
	ContentToolResult       ContentKind = "tool_result"
	ContentThinking         ContentKind = "thinking"
	ContentRedactedThinking ContentKind = "redacted_thinking"
)

// ImageData holds image content as either a URL or raw bytes.
type ImageData struct {
	URL       string `json:"url,omitempty"`
	Data      []byte `json:"data,omitempty"`
	MediaType string `json:"media_type,omitempty"`
	Detail    string `json:"detail,omitempty"` // "auto", "low", "high"
}

// AudioData holds audio content.
type AudioData struct {
	URL       string `json:"url,omitempty"`
	Data      []byte `json:"data,omitempty"`
	MediaType string `json:"media_type,omitempty"`
}

// DocumentData holds document content (PDF, etc.).
type DocumentData struct {
	URL       string `json:"url,omitempty"`
	Data      []byte `json:"data,omitempty"`
	MediaType string `json:"media_type,omitempty"`
	FileName  string `json:"file_name,omitempty"`
}

// ToolCallData represents a model-initiated tool invocation.
type ToolCallData struct {
	ID        string          `json:"id"`
	Name      string          `json:"name"`
	Arguments json.RawMessage `json:"arguments"`
	Type      string          `json:"type,omitempty"` // "function" (default)
}

// ToolResultData holds the result of a tool execution.
type ToolResultData struct {
	ToolCallID     string          `json:"tool_call_id"`
	Content        json.RawMessage `json:"content"`
	IsError        bool            `json:"is_error"`
	ImageData      []byte          `json:"image_data,omitempty"`
	ImageMediaType string          `json:"image_media_type,omitempty"`
}

// ThinkingData represents model reasoning/thinking content.
type ThinkingData struct {
	Text      string `json:"text"`
	Signature string `json:"signature,omitempty"`
	Redacted  bool   `json:"redacted"`
}

// ContentPart is a tagged union representing one part of a message.
type ContentPart struct {
	Kind       ContentKind     `json:"kind"`
	Text       string          `json:"text,omitempty"`
	Image      *ImageData      `json:"image,omitempty"`
	Audio      *AudioData      `json:"audio,omitempty"`
	Document   *DocumentData   `json:"document,omitempty"`
	ToolCall   *ToolCallData   `json:"tool_call,omitempty"`
	ToolResult *ToolResultData `json:"tool_result,omitempty"`
	Thinking   *ThinkingData   `json:"thinking,omitempty"`
}

// TextPart creates a text ContentPart.
func TextPart(text string) ContentPart {
	return ContentPart{Kind: ContentText, Text: text}
}

// ImageURLPart creates an image ContentPart from a URL.
func ImageURLPart(url, mediaType, detail string) ContentPart {
	return ContentPart{
		Kind:  ContentImage,
		Image: &ImageData{URL: url, MediaType: mediaType, Detail: detail},
	}
}

// ImageDataPart creates an image ContentPart from raw bytes.
func ImageDataPart(data []byte, mediaType, detail string) ContentPart {
	if mediaType == "" {
		mediaType = "image/png"
	}
	return ContentPart{
		Kind:  ContentImage,
		Image: &ImageData{Data: data, MediaType: mediaType, Detail: detail},
	}
}

// ToolCallPart creates a tool call ContentPart.
func ToolCallPart(id, name string, args json.RawMessage) ContentPart {
	return ContentPart{
		Kind:     ContentToolCall,
		ToolCall: &ToolCallData{ID: id, Name: name, Arguments: args, Type: "function"},
	}
}

// ToolResultPart creates a tool result ContentPart.
func ToolResultPart(toolCallID string, content json.RawMessage, isError bool) ContentPart {
	return ContentPart{
		Kind:       ContentToolResult,
		ToolResult: &ToolResultData{ToolCallID: toolCallID, Content: content, IsError: isError},
	}
}

// ThinkingPart creates a thinking ContentPart.
func ThinkingPart(text, signature string) ContentPart {
	return ContentPart{
		Kind:     ContentThinking,
		Thinking: &ThinkingData{Text: text, Signature: signature},
	}
}

// Message is the fundamental unit of conversation.
type Message struct {
	Role       Role          `json:"role"`
	Content    []ContentPart `json:"content"`
	Name       string        `json:"name,omitempty"`
	ToolCallID string        `json:"tool_call_id,omitempty"`
}

// TextContent returns the concatenation of all text content parts.
func (m Message) TextContent() string {
	var sb strings.Builder
	for _, part := range m.Content {
		if part.Kind == ContentText {
			sb.WriteString(part.Text)
		}
	}
	return sb.String()
}

// ToolCalls extracts all tool call data from the message content.
func (m Message) ToolCalls() []ToolCallData {
	var calls []ToolCallData
	for _, part := range m.Content {
		if part.Kind == ContentToolCall && part.ToolCall != nil {
			calls = append(calls, *part.ToolCall)
		}
	}
	return calls
}

// SystemMessage creates a system Message.
func SystemMessage(text string) Message {
	return Message{Role: RoleSystem, Content: []ContentPart{TextPart(text)}}
}

// UserMessage creates a user Message with text content.
func UserMessage(text string) Message {
	return Message{Role: RoleUser, Content: []ContentPart{TextPart(text)}}
}

// AssistantMessage creates an assistant Message with text content.
func AssistantMessage(text string) Message {
	return Message{Role: RoleAssistant, Content: []ContentPart{TextPart(text)}}
}

// ToolResultMessage creates a tool result Message.
func ToolResultMessage(toolCallID string, content string, isError bool) Message {
	raw, _ := json.Marshal(content)
	return Message{
		Role:       RoleTool,
		Content:    []ContentPart{ToolResultPart(toolCallID, raw, isError)},
		ToolCallID: toolCallID,
	}
}

// ToolChoice controls whether and how the model uses tools.
type ToolChoice struct {
	Mode     string `json:"mode"`                // "auto", "none", "required", "named"
	ToolName string `json:"tool_name,omitempty"` // required when mode is "named"
}

// Tool defines a tool the model can call.
type Tool struct {
	Name        string                                            `json:"name"`
	Description string                                            `json:"description"`
	Parameters  map[string]interface{}                            `json:"parameters"` // JSON Schema
	Execute     func(args json.RawMessage) (interface{}, error)   `json:"-"`          // active tool handler
}

// ToolCall is extracted from a model response.
type ToolCall struct {
	ID           string          `json:"id"`
	Name         string          `json:"name"`
	Arguments    json.RawMessage `json:"arguments"`
	RawArguments string          `json:"raw_arguments,omitempty"`
}

// ToolResult is produced by executing a tool.
type ToolResult struct {
	ToolCallID string      `json:"tool_call_id"`
	Content    interface{} `json:"content"`
	IsError    bool        `json:"is_error"`
}

// ResponseFormat specifies the desired output format.
type ResponseFormat struct {
	Type       string                 `json:"type"` // "text", "json", "json_schema"
	JSONSchema map[string]interface{} `json:"json_schema,omitempty"`
	Strict     bool                   `json:"strict,omitempty"`
}

// FinishReason describes why generation stopped.
type FinishReason struct {
	Reason string `json:"reason"` // "stop", "length", "tool_calls", "content_filter", "error", "other"
	Raw    string `json:"raw,omitempty"`
}

// Usage tracks token consumption.
type Usage struct {
	InputTokens     int                    `json:"input_tokens"`
	OutputTokens    int                    `json:"output_tokens"`
	TotalTokens     int                    `json:"total_tokens"`
	ReasoningTokens *int                   `json:"reasoning_tokens,omitempty"`
	CacheReadTokens *int                   `json:"cache_read_tokens,omitempty"`
	CacheWriteTokens *int                  `json:"cache_write_tokens,omitempty"`
	Raw             map[string]interface{} `json:"raw,omitempty"`
}

// Add returns a new Usage that is the sum of u and other.
func (u Usage) Add(other Usage) Usage {
	result := Usage{
		InputTokens:  u.InputTokens + other.InputTokens,
		OutputTokens: u.OutputTokens + other.OutputTokens,
		TotalTokens:  u.TotalTokens + other.TotalTokens,
	}
	result.ReasoningTokens = addOptionalInt(u.ReasoningTokens, other.ReasoningTokens)
	result.CacheReadTokens = addOptionalInt(u.CacheReadTokens, other.CacheReadTokens)
	result.CacheWriteTokens = addOptionalInt(u.CacheWriteTokens, other.CacheWriteTokens)
	return result
}

func addOptionalInt(a, b *int) *int {
	if a == nil && b == nil {
		return nil
	}
	va, vb := 0, 0
	if a != nil {
		va = *a
	}
	if b != nil {
		vb = *b
	}
	sum := va + vb
	return &sum
}

// Warning represents a non-fatal issue.
type Warning struct {
	Message string `json:"message"`
	Code    string `json:"code,omitempty"`
}

// RateLimitInfo contains rate limit metadata from response headers.
type RateLimitInfo struct {
	RequestsRemaining *int       `json:"requests_remaining,omitempty"`
	RequestsLimit     *int       `json:"requests_limit,omitempty"`
	TokensRemaining   *int       `json:"tokens_remaining,omitempty"`
	TokensLimit       *int       `json:"tokens_limit,omitempty"`
	ResetAt           *time.Time `json:"reset_at,omitempty"`
}

// Request is the input type for both complete() and stream().
type Request struct {
	Model           string                 `json:"model"`
	Messages        []Message              `json:"messages"`
	Provider        string                 `json:"provider,omitempty"`
	Tools           []Tool                 `json:"-"` // not serialized; contains execute handlers
	ToolDefs        []ToolDefinition       `json:"tools,omitempty"`
	ToolChoice      *ToolChoice            `json:"tool_choice,omitempty"`
	ResponseFormat  *ResponseFormat        `json:"response_format,omitempty"`
	Temperature     *float64               `json:"temperature,omitempty"`
	TopP            *float64               `json:"top_p,omitempty"`
	MaxTokens       *int                   `json:"max_tokens,omitempty"`
	StopSequences   []string               `json:"stop_sequences,omitempty"`
	ReasoningEffort string                 `json:"reasoning_effort,omitempty"`
	Metadata        map[string]string      `json:"metadata,omitempty"`
	ProviderOptions map[string]interface{} `json:"provider_options,omitempty"`
}

// ToolDefinition is the serializable part of a Tool (without execute handler).
type ToolDefinition struct {
	Name        string                 `json:"name"`
	Description string                 `json:"description"`
	Parameters  map[string]interface{} `json:"parameters"`
}

// Response is the output of complete().
type Response struct {
	ID           string                 `json:"id"`
	Model        string                 `json:"model"`
	Provider     string                 `json:"provider"`
	Message      Message                `json:"message"`
	FinishReason FinishReason           `json:"finish_reason"`
	Usage        Usage                  `json:"usage"`
	Raw          map[string]interface{} `json:"raw,omitempty"`
	Warnings     []Warning              `json:"warnings,omitempty"`
	RateLimit    *RateLimitInfo         `json:"rate_limit,omitempty"`
}

// Text returns the concatenated text from all text parts in the response message.
func (r Response) Text() string {
	return r.Message.TextContent()
}

// ToolCallsFromResponse extracts tool calls from the response message.
func (r Response) ToolCallsFromResponse() []ToolCall {
	var calls []ToolCall
	for _, part := range r.Message.Content {
		if part.Kind == ContentToolCall && part.ToolCall != nil {
			calls = append(calls, ToolCall{
				ID:        part.ToolCall.ID,
				Name:      part.ToolCall.Name,
				Arguments: part.ToolCall.Arguments,
			})
		}
	}
	return calls
}

// Reasoning returns concatenated reasoning text from thinking parts.
func (r Response) Reasoning() string {
	var sb strings.Builder
	for _, part := range r.Message.Content {
		if part.Kind == ContentThinking && part.Thinking != nil && !part.Thinking.Redacted {
			sb.WriteString(part.Thinking.Text)
		}
	}
	s := sb.String()
	if s == "" {
		return ""
	}
	return s
}

// StreamEventType identifies the kind of stream event.
type StreamEventType string

const (
	StreamStart      StreamEventType = "stream_start"
	TextStart        StreamEventType = "text_start"
	TextDelta        StreamEventType = "text_delta"
	TextEnd          StreamEventType = "text_end"
	ReasoningStart   StreamEventType = "reasoning_start"
	ReasoningDelta   StreamEventType = "reasoning_delta"
	ReasoningEnd     StreamEventType = "reasoning_end"
	ToolCallStart    StreamEventType = "tool_call_start"
	ToolCallDelta    StreamEventType = "tool_call_delta"
	ToolCallEnd      StreamEventType = "tool_call_end"
	StreamFinish     StreamEventType = "finish"
	StreamError      StreamEventType = "error"
	ProviderEvent    StreamEventType = "provider_event"
)

// StreamEvent is a single event from a streaming response.
type StreamEvent struct {
	Type           StreamEventType        `json:"type"`
	Delta          string                 `json:"delta,omitempty"`
	TextID         string                 `json:"text_id,omitempty"`
	ReasoningDelta string                 `json:"reasoning_delta,omitempty"`
	ToolCall       *ToolCall              `json:"tool_call,omitempty"`
	FinishReason   *FinishReason          `json:"finish_reason,omitempty"`
	Usage          *Usage                 `json:"usage,omitempty"`
	Response       *Response              `json:"response,omitempty"`
	Error          error                  `json:"-"`
	Raw            map[string]interface{} `json:"raw,omitempty"`
}

// TimeoutConfig configures timeout behavior.
type TimeoutConfig struct {
	Total   time.Duration `json:"total,omitempty"`
	PerStep time.Duration `json:"per_step,omitempty"`
}

// StopCondition is a function that decides whether the tool loop should stop.
type StopCondition func(steps []StepResult) bool

// GenerateResult is returned by the high-level generate() function.
type GenerateResult struct {
	Text         string       `json:"text"`
	Reasoning    string       `json:"reasoning,omitempty"`
	ToolCalls    []ToolCall   `json:"tool_calls,omitempty"`
	ToolResults  []ToolResult `json:"tool_results,omitempty"`
	FinishReason FinishReason `json:"finish_reason"`
	Usage        Usage        `json:"usage"`
	TotalUsage   Usage        `json:"total_usage"`
	Steps        []StepResult `json:"steps"`
	Response     Response     `json:"response"`
	Output       interface{}  `json:"output,omitempty"` // for generate_object
}

// StepResult tracks a single step in a multi-step generation.
type StepResult struct {
	Text         string       `json:"text"`
	Reasoning    string       `json:"reasoning,omitempty"`
	ToolCalls    []ToolCall   `json:"tool_calls,omitempty"`
	ToolResults  []ToolResult `json:"tool_results,omitempty"`
	FinishReason FinishReason `json:"finish_reason"`
	Usage        Usage        `json:"usage"`
	Response     Response     `json:"response"`
	Warnings     []Warning    `json:"warnings,omitempty"`
}
