package unifiedllm

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestRetryPolicyDelay(t *testing.T) {
	policy := RetryPolicy{
		BaseDelay:         1.0,
		BackoffMultiplier: 2.0,
		MaxDelay:          60.0,
		Jitter:            false,
	}

	delays := []time.Duration{
		1 * time.Second,
		2 * time.Second,
		4 * time.Second,
		8 * time.Second,
		16 * time.Second,
	}

	for i, expected := range delays {
		got := policy.Delay(i)
		if got != expected {
			t.Errorf("attempt %d: expected %v, got %v", i, expected, got)
		}
	}
}

func TestRetryPolicyDelayWithMaxCap(t *testing.T) {
	policy := RetryPolicy{
		BaseDelay:         1.0,
		BackoffMultiplier: 2.0,
		MaxDelay:          5.0,
		Jitter:            false,
	}

	// Attempt 10 would be 1024s without cap.
	got := policy.Delay(10)
	if got != 5*time.Second {
		t.Errorf("expected 5s (capped), got %v", got)
	}
}

func TestRetryPolicyDelayWithJitter(t *testing.T) {
	policy := RetryPolicy{
		BaseDelay:         1.0,
		BackoffMultiplier: 2.0,
		MaxDelay:          60.0,
		Jitter:            true,
	}

	// With jitter, delay should be within +/- 50% of base delay.
	for i := 0; i < 100; i++ {
		got := policy.Delay(0)
		if got < 500*time.Millisecond || got > 1500*time.Millisecond {
			t.Errorf("jittered delay out of range: %v", got)
		}
	}
}

func TestRetrySuccess(t *testing.T) {
	policy := RetryPolicy{MaxRetries: 3, BaseDelay: 0.001, BackoffMultiplier: 1, MaxDelay: 0.001, Jitter: false}

	callCount := 0
	result, err := Retry(context.Background(), policy, func(ctx context.Context) (string, error) {
		callCount++
		if callCount < 3 {
			return "", &ServerError{ProviderError: ProviderError{
				SDKError: SDKError{Message: "server error"}, Retryable: true,
			}}
		}
		return "success", nil
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != "success" {
		t.Errorf("expected %q, got %q", "success", result)
	}
	if callCount != 3 {
		t.Errorf("expected 3 calls, got %d", callCount)
	}
}

func TestRetryNonRetryableError(t *testing.T) {
	policy := RetryPolicy{MaxRetries: 3, BaseDelay: 0.001, BackoffMultiplier: 1, MaxDelay: 0.001, Jitter: false}

	callCount := 0
	_, err := Retry(context.Background(), policy, func(ctx context.Context) (string, error) {
		callCount++
		return "", &AuthenticationError{ProviderError: ProviderError{
			SDKError: SDKError{Message: "invalid key"},
		}}
	})
	if err == nil {
		t.Fatal("expected error")
	}
	if callCount != 1 {
		t.Errorf("expected 1 call (no retries for non-retryable), got %d", callCount)
	}
}

func TestRetryExhausted(t *testing.T) {
	policy := RetryPolicy{MaxRetries: 2, BaseDelay: 0.001, BackoffMultiplier: 1, MaxDelay: 0.001, Jitter: false}

	callCount := 0
	_, err := Retry(context.Background(), policy, func(ctx context.Context) (string, error) {
		callCount++
		return "", &ServerError{ProviderError: ProviderError{
			SDKError: SDKError{Message: "server error"}, Retryable: true,
		}}
	})
	if err == nil {
		t.Fatal("expected error after retries exhausted")
	}
	if callCount != 3 { // 1 initial + 2 retries
		t.Errorf("expected 3 calls, got %d", callCount)
	}
}

func TestRetryCancelled(t *testing.T) {
	policy := RetryPolicy{MaxRetries: 5, BaseDelay: 1.0, BackoffMultiplier: 1, MaxDelay: 1.0, Jitter: false}

	ctx, cancel := context.WithCancel(context.Background())
	callCount := 0
	go func() {
		time.Sleep(50 * time.Millisecond)
		cancel()
	}()

	_, err := Retry(ctx, policy, func(ctx context.Context) (string, error) {
		callCount++
		return "", errors.New("always fails")
	})
	if err == nil {
		t.Fatal("expected error")
	}
	// Should have been cancelled before all retries completed.
	if callCount > 3 {
		t.Errorf("expected fewer calls due to cancellation, got %d", callCount)
	}
}

func TestRetryNoError(t *testing.T) {
	policy := DefaultRetryPolicy()
	result, err := Retry(context.Background(), policy, func(ctx context.Context) (string, error) {
		return "immediate", nil
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result != "immediate" {
		t.Errorf("expected %q, got %q", "immediate", result)
	}
}

func TestDefaultRetryPolicy(t *testing.T) {
	p := DefaultRetryPolicy()
	if p.MaxRetries != 2 {
		t.Errorf("expected max_retries 2, got %d", p.MaxRetries)
	}
	if p.BaseDelay != 1.0 {
		t.Errorf("expected base_delay 1.0, got %f", p.BaseDelay)
	}
	if p.MaxDelay != 60.0 {
		t.Errorf("expected max_delay 60.0, got %f", p.MaxDelay)
	}
	if p.BackoffMultiplier != 2.0 {
		t.Errorf("expected backoff_multiplier 2.0, got %f", p.BackoffMultiplier)
	}
	if !p.Jitter {
		t.Error("expected jitter = true")
	}
}
