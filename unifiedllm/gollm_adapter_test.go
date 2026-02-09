package unifiedllm

import (
	"testing"
)

func TestGollmAdapterName(t *testing.T) {
	// Test that we can create adapters for known providers.
	// Note: These will fail if the environment doesn't have API keys,
	// but we test the Name() method behavior.
	for _, provider := range []string{"openai", "anthropic"} {
		adapter, err := NewGollmAdapter(provider, "test-key-not-real")
		if err != nil {
			t.Logf("skipping %s adapter creation (expected without real key): %v", provider, err)
			continue
		}
		if adapter.Name() != provider {
			t.Errorf("expected name %q, got %q", provider, adapter.Name())
		}
	}
}

func TestGollmAdapterTranslateError(t *testing.T) {
	adapter := &GollmAdapter{provider: "openai"}

	tests := []struct {
		errMsg   string
		expected string
	}{
		{"401 Unauthorized", "*unifiedllm.AuthenticationError"},
		{"invalid api key", "*unifiedllm.AuthenticationError"},
		{"403 Forbidden", "*unifiedllm.AccessDeniedError"},
		{"404 not found", "*unifiedllm.NotFoundError"},
		{"429 rate limit exceeded", "*unifiedllm.RateLimitError"},
		{"context length exceeded", "*unifiedllm.ContextLengthError"},
		{"500 internal server error", "*unifiedllm.ServerError"},
		{"timeout waiting for response", "*unifiedllm.RequestTimeoutError"},
		{"content filter triggered", "*unifiedllm.ContentFilterError"},
		{"something unknown", "*unifiedllm.ProviderError"},
	}

	for _, tt := range tests {
		err := adapter.translateError(errForMsg(tt.errMsg))
		if err == nil {
			t.Errorf("expected non-nil error for %q", tt.errMsg)
			continue
		}
		// Verify the error is classifiable.
		switch tt.expected {
		case "*unifiedllm.AuthenticationError":
			if _, ok := err.(*AuthenticationError); !ok {
				t.Errorf("for %q: expected AuthenticationError, got %T", tt.errMsg, err)
			}
		case "*unifiedllm.AccessDeniedError":
			if _, ok := err.(*AccessDeniedError); !ok {
				t.Errorf("for %q: expected AccessDeniedError, got %T", tt.errMsg, err)
			}
		case "*unifiedllm.NotFoundError":
			if _, ok := err.(*NotFoundError); !ok {
				t.Errorf("for %q: expected NotFoundError, got %T", tt.errMsg, err)
			}
		case "*unifiedllm.RateLimitError":
			if _, ok := err.(*RateLimitError); !ok {
				t.Errorf("for %q: expected RateLimitError, got %T", tt.errMsg, err)
			}
		case "*unifiedllm.ContextLengthError":
			if _, ok := err.(*ContextLengthError); !ok {
				t.Errorf("for %q: expected ContextLengthError, got %T", tt.errMsg, err)
			}
		case "*unifiedllm.ServerError":
			if _, ok := err.(*ServerError); !ok {
				t.Errorf("for %q: expected ServerError, got %T", tt.errMsg, err)
			}
		case "*unifiedllm.RequestTimeoutError":
			if _, ok := err.(*RequestTimeoutError); !ok {
				t.Errorf("for %q: expected RequestTimeoutError, got %T", tt.errMsg, err)
			}
		case "*unifiedllm.ContentFilterError":
			if _, ok := err.(*ContentFilterError); !ok {
				t.Errorf("for %q: expected ContentFilterError, got %T", tt.errMsg, err)
			}
		case "*unifiedllm.ProviderError":
			if _, ok := err.(*ProviderError); !ok {
				t.Errorf("for %q: expected ProviderError, got %T", tt.errMsg, err)
			}
		}
	}
}

type simpleError struct{ msg string }

func (e *simpleError) Error() string { return e.msg }
func errForMsg(msg string) error     { return &simpleError{msg: msg} }

func TestGollmAdapterSupportsToolChoice(t *testing.T) {
	adapter := &GollmAdapter{provider: "openai"}

	if !adapter.SupportsToolChoice("auto") {
		t.Error("expected auto to be supported")
	}
	if !adapter.SupportsToolChoice("none") {
		t.Error("expected none to be supported")
	}
	if !adapter.SupportsToolChoice("required") {
		t.Error("expected required to be supported")
	}
	if !adapter.SupportsToolChoice("named") {
		t.Error("expected named to be supported for openai")
	}
	if adapter.SupportsToolChoice("invalid") {
		t.Error("expected invalid to not be supported")
	}

	geminiAdapter := &GollmAdapter{provider: "gemini"}
	if geminiAdapter.SupportsToolChoice("named") {
		t.Error("expected named to not be supported for gemini")
	}
}

func TestEstimateTokens(t *testing.T) {
	req := Request{
		Messages: []Message{
			UserMessage("Hello world, this is a test message."),
		},
	}
	tokens := estimateTokens(req)
	if tokens <= 0 {
		t.Errorf("expected positive token estimate, got %d", tokens)
	}
}

func TestEstimateTokensEmpty(t *testing.T) {
	req := Request{Messages: []Message{}}
	tokens := estimateTokens(req)
	if tokens != 10 {
		t.Errorf("expected default token estimate of 10, got %d", tokens)
	}
}
