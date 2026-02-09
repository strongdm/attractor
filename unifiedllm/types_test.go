package unifiedllm

import (
	"encoding/json"
	"testing"
)

func TestMessageConstructors(t *testing.T) {
	t.Run("SystemMessage", func(t *testing.T) {
		msg := SystemMessage("You are helpful.")
		if msg.Role != RoleSystem {
			t.Errorf("expected role %q, got %q", RoleSystem, msg.Role)
		}
		if msg.TextContent() != "You are helpful." {
			t.Errorf("expected text %q, got %q", "You are helpful.", msg.TextContent())
		}
	})

	t.Run("UserMessage", func(t *testing.T) {
		msg := UserMessage("Hello")
		if msg.Role != RoleUser {
			t.Errorf("expected role %q, got %q", RoleUser, msg.Role)
		}
		if msg.TextContent() != "Hello" {
			t.Errorf("expected text %q, got %q", "Hello", msg.TextContent())
		}
	})

	t.Run("AssistantMessage", func(t *testing.T) {
		msg := AssistantMessage("Hi there")
		if msg.Role != RoleAssistant {
			t.Errorf("expected role %q, got %q", RoleAssistant, msg.Role)
		}
		if msg.TextContent() != "Hi there" {
			t.Errorf("expected text %q, got %q", "Hi there", msg.TextContent())
		}
	})

	t.Run("ToolResultMessage", func(t *testing.T) {
		msg := ToolResultMessage("call_123", "72F and sunny", false)
		if msg.Role != RoleTool {
			t.Errorf("expected role %q, got %q", RoleTool, msg.Role)
		}
		if msg.ToolCallID != "call_123" {
			t.Errorf("expected tool_call_id %q, got %q", "call_123", msg.ToolCallID)
		}
		if len(msg.Content) != 1 {
			t.Fatalf("expected 1 content part, got %d", len(msg.Content))
		}
		if msg.Content[0].Kind != ContentToolResult {
			t.Errorf("expected kind %q, got %q", ContentToolResult, msg.Content[0].Kind)
		}
	})
}

func TestContentPartConstructors(t *testing.T) {
	t.Run("TextPart", func(t *testing.T) {
		part := TextPart("hello")
		if part.Kind != ContentText {
			t.Errorf("expected kind %q, got %q", ContentText, part.Kind)
		}
		if part.Text != "hello" {
			t.Errorf("expected text %q, got %q", "hello", part.Text)
		}
	})

	t.Run("ImageURLPart", func(t *testing.T) {
		part := ImageURLPart("https://example.com/img.png", "image/png", "auto")
		if part.Kind != ContentImage {
			t.Errorf("expected kind %q, got %q", ContentImage, part.Kind)
		}
		if part.Image == nil {
			t.Fatal("expected image data, got nil")
		}
		if part.Image.URL != "https://example.com/img.png" {
			t.Errorf("expected URL %q, got %q", "https://example.com/img.png", part.Image.URL)
		}
	})

	t.Run("ImageDataPart default media type", func(t *testing.T) {
		part := ImageDataPart([]byte{1, 2, 3}, "", "high")
		if part.Image.MediaType != "image/png" {
			t.Errorf("expected default media type image/png, got %q", part.Image.MediaType)
		}
	})

	t.Run("ToolCallPart", func(t *testing.T) {
		args := json.RawMessage(`{"city": "SF"}`)
		part := ToolCallPart("call_1", "get_weather", args)
		if part.Kind != ContentToolCall {
			t.Errorf("expected kind %q, got %q", ContentToolCall, part.Kind)
		}
		if part.ToolCall.Name != "get_weather" {
			t.Errorf("expected name %q, got %q", "get_weather", part.ToolCall.Name)
		}
	})

	t.Run("ThinkingPart", func(t *testing.T) {
		part := ThinkingPart("Let me think...", "sig_abc")
		if part.Kind != ContentThinking {
			t.Errorf("expected kind %q, got %q", ContentThinking, part.Kind)
		}
		if part.Thinking.Signature != "sig_abc" {
			t.Errorf("expected signature %q, got %q", "sig_abc", part.Thinking.Signature)
		}
	})
}

func TestMessageTextContent(t *testing.T) {
	msg := Message{
		Role: RoleAssistant,
		Content: []ContentPart{
			TextPart("Hello "),
			ThinkingPart("thinking...", ""),
			TextPart("world"),
		},
	}
	text := msg.TextContent()
	if text != "Hello world" {
		t.Errorf("expected %q, got %q", "Hello world", text)
	}
}

func TestMessageToolCalls(t *testing.T) {
	args1 := json.RawMessage(`{"city":"SF"}`)
	args2 := json.RawMessage(`{"city":"NYC"}`)
	msg := Message{
		Role: RoleAssistant,
		Content: []ContentPart{
			TextPart("Let me check the weather."),
			ToolCallPart("call_1", "get_weather", args1),
			ToolCallPart("call_2", "get_weather", args2),
		},
	}
	calls := msg.ToolCalls()
	if len(calls) != 2 {
		t.Fatalf("expected 2 tool calls, got %d", len(calls))
	}
	if calls[0].Name != "get_weather" {
		t.Errorf("expected name %q, got %q", "get_weather", calls[0].Name)
	}
}

func TestUsageAdd(t *testing.T) {
	a := Usage{InputTokens: 10, OutputTokens: 20, TotalTokens: 30}
	b := Usage{InputTokens: 5, OutputTokens: 15, TotalTokens: 20}
	result := a.Add(b)

	if result.InputTokens != 15 {
		t.Errorf("expected input_tokens 15, got %d", result.InputTokens)
	}
	if result.OutputTokens != 35 {
		t.Errorf("expected output_tokens 35, got %d", result.OutputTokens)
	}
	if result.TotalTokens != 50 {
		t.Errorf("expected total_tokens 50, got %d", result.TotalTokens)
	}
	if result.ReasoningTokens != nil {
		t.Errorf("expected reasoning_tokens nil, got %v", result.ReasoningTokens)
	}
}

func TestUsageAddOptionalFields(t *testing.T) {
	five := 5
	ten := 10
	a := Usage{InputTokens: 10, OutputTokens: 20, TotalTokens: 30, ReasoningTokens: &five}
	b := Usage{InputTokens: 5, OutputTokens: 15, TotalTokens: 20, ReasoningTokens: &ten}
	result := a.Add(b)

	if result.ReasoningTokens == nil {
		t.Fatal("expected non-nil reasoning_tokens")
	}
	if *result.ReasoningTokens != 15 {
		t.Errorf("expected reasoning_tokens 15, got %d", *result.ReasoningTokens)
	}
}

func TestUsageAddOneNilOptional(t *testing.T) {
	five := 5
	a := Usage{CacheReadTokens: &five}
	b := Usage{}
	result := a.Add(b)

	if result.CacheReadTokens == nil {
		t.Fatal("expected non-nil cache_read_tokens")
	}
	if *result.CacheReadTokens != 5 {
		t.Errorf("expected cache_read_tokens 5, got %d", *result.CacheReadTokens)
	}
}

func TestResponseAccessors(t *testing.T) {
	resp := Response{
		Message: Message{
			Role: RoleAssistant,
			Content: []ContentPart{
				ThinkingPart("reasoning here", "sig"),
				TextPart("The answer is 42."),
				ToolCallPart("call_1", "calc", json.RawMessage(`{}`)),
			},
		},
	}

	if resp.Text() != "The answer is 42." {
		t.Errorf("expected text %q, got %q", "The answer is 42.", resp.Text())
	}

	if resp.Reasoning() != "reasoning here" {
		t.Errorf("expected reasoning %q, got %q", "reasoning here", resp.Reasoning())
	}

	calls := resp.ToolCallsFromResponse()
	if len(calls) != 1 {
		t.Fatalf("expected 1 tool call, got %d", len(calls))
	}
	if calls[0].Name != "calc" {
		t.Errorf("expected tool name %q, got %q", "calc", calls[0].Name)
	}
}

func TestFinishReasonValues(t *testing.T) {
	cases := []struct {
		reason string
		valid  bool
	}{
		{"stop", true},
		{"length", true},
		{"tool_calls", true},
		{"content_filter", true},
		{"error", true},
		{"other", true},
	}
	for _, tc := range cases {
		fr := FinishReason{Reason: tc.reason}
		if fr.Reason != tc.reason {
			t.Errorf("expected reason %q, got %q", tc.reason, fr.Reason)
		}
	}
}
