package unifiedllm

import (
	"errors"
	"testing"
)

func TestErrorFromStatusCode(t *testing.T) {
	tests := []struct {
		status     int
		expectType string
		retryable  bool
	}{
		{400, "*unifiedllm.InvalidRequestError", false},
		{401, "*unifiedllm.AuthenticationError", false},
		{403, "*unifiedllm.AccessDeniedError", false},
		{404, "*unifiedllm.NotFoundError", false},
		{408, "*unifiedllm.RequestTimeoutError", true},
		{413, "*unifiedllm.ContextLengthError", false},
		{422, "*unifiedllm.InvalidRequestError", false},
		{429, "*unifiedllm.RateLimitError", true},
		{500, "*unifiedllm.ServerError", true},
		{502, "*unifiedllm.ServerError", true},
		{503, "*unifiedllm.ServerError", true},
		{504, "*unifiedllm.ServerError", true},
	}

	for _, tt := range tests {
		err := ErrorFromStatusCode(tt.status, "test error", "openai", "", nil, nil)
		if !IsRetryable(err) && tt.retryable {
			t.Errorf("status %d: expected retryable=true", tt.status)
		}
		if IsRetryable(err) && !tt.retryable {
			t.Errorf("status %d: expected retryable=false", tt.status)
		}
	}
}

func TestIsRetryable(t *testing.T) {
	tests := []struct {
		name      string
		err       error
		retryable bool
	}{
		{"nil", nil, false},
		{"auth error", &AuthenticationError{}, false},
		{"access denied", &AccessDeniedError{}, false},
		{"not found", &NotFoundError{}, false},
		{"invalid request", &InvalidRequestError{}, false},
		{"context length", &ContextLengthError{}, false},
		{"quota exceeded", &QuotaExceededError{}, false},
		{"content filter", &ContentFilterError{}, false},
		{"config error", &ConfigurationError{}, false},
		{"rate limit", &RateLimitError{ProviderError: ProviderError{Retryable: true}}, true},
		{"server error", &ServerError{ProviderError: ProviderError{Retryable: true}}, true},
		{"network error", &NetworkError{}, true},
		{"stream error", &StreamErrorType{}, true},
		{"timeout error", &RequestTimeoutError{}, true},
		{"unknown error", errors.New("unknown"), true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := IsRetryable(tt.err)
			if got != tt.retryable {
				t.Errorf("IsRetryable(%T) = %v, want %v", tt.err, got, tt.retryable)
			}
		})
	}
}

func TestSDKErrorUnwrap(t *testing.T) {
	cause := errors.New("root cause")
	err := &SDKError{Message: "wrapper", Cause: cause}
	if !errors.Is(err, cause) {
		t.Error("expected SDKError to unwrap to its cause")
	}
}

func TestProviderErrorMessage(t *testing.T) {
	err := &ProviderError{
		SDKError:   SDKError{Message: "rate limit exceeded"},
		Provider:   "openai",
		StatusCode: 429,
		Retryable:  true,
	}
	msg := err.Error()
	if msg == "" {
		t.Error("expected non-empty error message")
	}
	if !contains(msg, "openai") || !contains(msg, "rate limit") {
		t.Errorf("error message missing expected content: %q", msg)
	}
}

func contains(s, sub string) bool {
	return len(s) >= len(sub) && containsStr(s, sub)
}

func containsStr(s, sub string) bool {
	for i := 0; i <= len(s)-len(sub); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
