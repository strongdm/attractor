package unifiedllm

import (
	"context"
	"encoding/json"
	"testing"
)

// mockAdapter is a test double for ProviderAdapter.
type mockAdapter struct {
	name     string
	response *Response
	err      error
	events   []StreamEvent
}

func (m *mockAdapter) Name() string { return m.name }

func (m *mockAdapter) Complete(ctx context.Context, req Request) (*Response, error) {
	if m.err != nil {
		return nil, m.err
	}
	return m.response, nil
}

func (m *mockAdapter) Stream(ctx context.Context, req Request) (<-chan StreamEvent, error) {
	if m.err != nil {
		return nil, m.err
	}
	ch := make(chan StreamEvent, len(m.events))
	for _, e := range m.events {
		ch <- e
	}
	close(ch)
	return ch, nil
}

func newMockAdapter(name, text string) *mockAdapter {
	return &mockAdapter{
		name: name,
		response: &Response{
			ID:       "test_resp",
			Model:    "test-model",
			Provider: name,
			Message: Message{
				Role:    RoleAssistant,
				Content: []ContentPart{TextPart(text)},
			},
			FinishReason: FinishReason{Reason: "stop"},
			Usage:        Usage{InputTokens: 10, OutputTokens: 20, TotalTokens: 30},
		},
	}
}

func TestClientComplete(t *testing.T) {
	mock := newMockAdapter("test-provider", "Hello!")
	client := NewClient(
		WithProvider("test-provider", mock),
		WithDefaultProvider("test-provider"),
	)

	resp, err := client.Complete(context.Background(), Request{
		Model:    "test-model",
		Messages: []Message{UserMessage("Hi")},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Text() != "Hello!" {
		t.Errorf("expected text %q, got %q", "Hello!", resp.Text())
	}
	if resp.Provider != "test-provider" {
		t.Errorf("expected provider %q, got %q", "test-provider", resp.Provider)
	}
}

func TestClientProviderRouting(t *testing.T) {
	openai := newMockAdapter("openai", "OpenAI response")
	anthropic := newMockAdapter("anthropic", "Anthropic response")

	client := NewClient(
		WithProvider("openai", openai),
		WithProvider("anthropic", anthropic),
		WithDefaultProvider("openai"),
	)

	// Explicit provider.
	resp, err := client.Complete(context.Background(), Request{
		Model:    "claude-opus-4-6",
		Messages: []Message{UserMessage("Hi")},
		Provider: "anthropic",
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Text() != "Anthropic response" {
		t.Errorf("expected Anthropic response, got %q", resp.Text())
	}

	// Default provider.
	resp, err = client.Complete(context.Background(), Request{
		Model:    "gpt-5.2",
		Messages: []Message{UserMessage("Hi")},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Text() != "OpenAI response" {
		t.Errorf("expected OpenAI response, got %q", resp.Text())
	}
}

func TestClientNoProvider(t *testing.T) {
	client := NewClient()
	_, err := client.Complete(context.Background(), Request{
		Model:    "test-model",
		Messages: []Message{UserMessage("Hi")},
	})
	if err == nil {
		t.Fatal("expected error for no provider")
	}
	if _, ok := err.(*ConfigurationError); !ok {
		t.Errorf("expected ConfigurationError, got %T", err)
	}
}

func TestClientMiddleware(t *testing.T) {
	mock := newMockAdapter("test", "response")
	called := false

	mw := func(ctx context.Context, req Request, next func(context.Context, Request) (*Response, error)) (*Response, error) {
		called = true
		return next(ctx, req)
	}

	client := NewClient(
		WithProvider("test", mock),
		WithMiddleware(mw),
	)

	_, err := client.Complete(context.Background(), Request{
		Model:    "test-model",
		Messages: []Message{UserMessage("Hi")},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !called {
		t.Error("middleware was not called")
	}
}

func TestClientMiddlewareOrder(t *testing.T) {
	mock := newMockAdapter("test", "response")
	var order []int

	mw1 := func(ctx context.Context, req Request, next func(context.Context, Request) (*Response, error)) (*Response, error) {
		order = append(order, 1)
		resp, err := next(ctx, req)
		order = append(order, -1)
		return resp, err
	}
	mw2 := func(ctx context.Context, req Request, next func(context.Context, Request) (*Response, error)) (*Response, error) {
		order = append(order, 2)
		resp, err := next(ctx, req)
		order = append(order, -2)
		return resp, err
	}

	client := NewClient(
		WithProvider("test", mock),
		WithMiddleware(mw1, mw2),
	)

	_, err := client.Complete(context.Background(), Request{
		Model:    "test-model",
		Messages: []Message{UserMessage("Hi")},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Onion pattern: first registered runs first for request, reverse for response.
	expected := []int{1, 2, -2, -1}
	if len(order) != len(expected) {
		t.Fatalf("expected %d middleware calls, got %d", len(expected), len(order))
	}
	for i, v := range expected {
		if order[i] != v {
			t.Errorf("position %d: expected %d, got %d", i, v, order[i])
		}
	}
}

func TestClientStream(t *testing.T) {
	mock := &mockAdapter{
		name: "test",
		events: []StreamEvent{
			{Type: StreamStart},
			{Type: TextStart, TextID: "t0"},
			{Type: TextDelta, Delta: "Hello", TextID: "t0"},
			{Type: TextDelta, Delta: " world", TextID: "t0"},
			{Type: TextEnd, TextID: "t0"},
			{Type: StreamFinish, FinishReason: &FinishReason{Reason: "stop"}},
		},
	}

	client := NewClient(WithProvider("test", mock))
	ch, err := client.Stream(context.Background(), Request{
		Model:    "test-model",
		Messages: []Message{UserMessage("Hi")},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	var events []StreamEvent
	for event := range ch {
		events = append(events, event)
	}
	if len(events) != 6 {
		t.Fatalf("expected 6 events, got %d", len(events))
	}
	if events[0].Type != StreamStart {
		t.Errorf("expected StreamStart, got %q", events[0].Type)
	}
	if events[2].Delta != "Hello" {
		t.Errorf("expected delta %q, got %q", "Hello", events[2].Delta)
	}
}

func TestClientRegisterProvider(t *testing.T) {
	client := NewClient()
	mock := newMockAdapter("dynamic", "dynamic response")
	client.RegisterProvider("dynamic", mock)

	resp, err := client.Complete(context.Background(), Request{
		Model:    "test-model",
		Messages: []Message{UserMessage("Hi")},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Text() != "dynamic response" {
		t.Errorf("expected %q, got %q", "dynamic response", resp.Text())
	}
}

func TestClientAutoSingleProviderDefault(t *testing.T) {
	mock := newMockAdapter("only", "only response")
	client := NewClient(WithProvider("only", mock))

	resp, err := client.Complete(context.Background(), Request{
		Model:    "test-model",
		Messages: []Message{UserMessage("Hi")},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Text() != "only response" {
		t.Errorf("expected %q, got %q", "only response", resp.Text())
	}
}

func TestGenerateWithMock(t *testing.T) {
	mock := newMockAdapter("test", "Generated response")
	client := NewClient(WithProvider("test", mock))

	result, err := Generate(context.Background(), GenerateOptions{
		Model:    "test-model",
		Prompt:   "Say hello",
		Provider: "test",
		Client:   client,
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Text != "Generated response" {
		t.Errorf("expected %q, got %q", "Generated response", result.Text)
	}
	if result.FinishReason.Reason != "stop" {
		t.Errorf("expected finish reason %q, got %q", "stop", result.FinishReason.Reason)
	}
	if len(result.Steps) != 1 {
		t.Errorf("expected 1 step, got %d", len(result.Steps))
	}
}

func TestGenerateWithMessages(t *testing.T) {
	mock := newMockAdapter("test", "Response to conversation")
	client := NewClient(WithProvider("test", mock))

	result, err := Generate(context.Background(), GenerateOptions{
		Model: "test-model",
		Messages: []Message{
			SystemMessage("Be helpful"),
			UserMessage("What is 2+2?"),
		},
		Provider: "test",
		Client:   client,
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Text != "Response to conversation" {
		t.Errorf("expected %q, got %q", "Response to conversation", result.Text)
	}
}

func TestGenerateBothPromptAndMessages(t *testing.T) {
	client := NewClient(WithProvider("test", newMockAdapter("test", "x")))
	_, err := Generate(context.Background(), GenerateOptions{
		Model:    "test-model",
		Prompt:   "hello",
		Messages: []Message{UserMessage("hello")},
		Provider: "test",
		Client:   client,
	})
	if err == nil {
		t.Fatal("expected error when both prompt and messages provided")
	}
}

func TestGenerateWithActiveTools(t *testing.T) {
	callCount := 0
	toolResponse := &Response{
		ID:       "resp_tool",
		Model:    "test-model",
		Provider: "test",
		Message: Message{
			Role: RoleAssistant,
			Content: []ContentPart{
				ToolCallPart("call_1", "get_weather", json.RawMessage(`{"city":"SF"}`)),
			},
		},
		FinishReason: FinishReason{Reason: "tool_calls"},
		Usage:        Usage{InputTokens: 10, OutputTokens: 5, TotalTokens: 15},
	}
	textResponse := newMockAdapter("test", "It's 72F in SF").response

	mock := &mockAdapter{name: "test"}
	// Return tool call on first call, text on second.
	origComplete := mock.Complete
	_ = origComplete
	mock.response = toolResponse

	// Use a custom adapter that alternates responses.
	adapter := &sequenceAdapter{
		name:      "test",
		responses: []*Response{toolResponse, textResponse},
	}

	client := NewClient(WithProvider("test", adapter))

	weatherTool := Tool{
		Name:        "get_weather",
		Description: "Get weather",
		Parameters: map[string]interface{}{
			"type": "object",
			"properties": map[string]interface{}{
				"city": map[string]interface{}{"type": "string"},
			},
		},
		Execute: func(args json.RawMessage) (interface{}, error) {
			callCount++
			return "72F and sunny", nil
		},
	}

	result, err := Generate(context.Background(), GenerateOptions{
		Model:         "test-model",
		Prompt:        "What's the weather in SF?",
		Tools:         []Tool{weatherTool},
		MaxToolRounds: 3,
		Provider:      "test",
		Client:        client,
		MaxRetries:    0,
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if callCount != 1 {
		t.Errorf("expected tool to be called once, got %d", callCount)
	}
	if len(result.Steps) != 2 {
		t.Errorf("expected 2 steps, got %d", len(result.Steps))
	}
	if result.Text != "It's 72F in SF" {
		t.Errorf("expected final text %q, got %q", "It's 72F in SF", result.Text)
	}
}

// sequenceAdapter returns responses in sequence.
type sequenceAdapter struct {
	name      string
	responses []*Response
	idx       int
}

func (s *sequenceAdapter) Name() string { return s.name }

func (s *sequenceAdapter) Complete(ctx context.Context, req Request) (*Response, error) {
	if s.idx >= len(s.responses) {
		return s.responses[len(s.responses)-1], nil
	}
	resp := s.responses[s.idx]
	s.idx++
	return resp, nil
}

func (s *sequenceAdapter) Stream(ctx context.Context, req Request) (<-chan StreamEvent, error) {
	ch := make(chan StreamEvent)
	close(ch)
	return ch, nil
}

func TestStreamAccumulator(t *testing.T) {
	acc := NewStreamAccumulator()

	events := []StreamEvent{
		{Type: StreamStart},
		{Type: TextStart, TextID: "t0"},
		{Type: TextDelta, Delta: "Hello ", TextID: "t0"},
		{Type: TextDelta, Delta: "world", TextID: "t0"},
		{Type: TextEnd, TextID: "t0"},
		{Type: StreamFinish, FinishReason: &FinishReason{Reason: "stop"}, Usage: &Usage{InputTokens: 5, OutputTokens: 10, TotalTokens: 15}},
	}

	for _, e := range events {
		acc.Process(e)
	}

	resp := acc.Response()
	if resp.Text() != "Hello world" {
		t.Errorf("expected accumulated text %q, got %q", "Hello world", resp.Text())
	}
	if resp.FinishReason.Reason != "stop" {
		t.Errorf("expected finish reason %q, got %q", "stop", resp.FinishReason.Reason)
	}
	if resp.Usage.TotalTokens != 15 {
		t.Errorf("expected total_tokens 15, got %d", resp.Usage.TotalTokens)
	}
}
