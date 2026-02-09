package unifiedllm

import (
	"context"
	"math"
	"math/rand"
	"time"
)

// RetryPolicy configures retry behavior with exponential backoff.
type RetryPolicy struct {
	MaxRetries        int     // total retry attempts (not counting initial)
	BaseDelay         float64 // initial delay in seconds
	MaxDelay          float64 // maximum delay between retries
	BackoffMultiplier float64 // exponential backoff factor
	Jitter            bool    // add random jitter to prevent thundering herd
	OnRetry           func(err error, attempt int, delay time.Duration)
}

// DefaultRetryPolicy returns the spec-default retry policy.
func DefaultRetryPolicy() RetryPolicy {
	return RetryPolicy{
		MaxRetries:        2,
		BaseDelay:         1.0,
		MaxDelay:          60.0,
		BackoffMultiplier: 2.0,
		Jitter:            true,
	}
}

// Delay calculates the delay for attempt n (0-indexed).
func (p RetryPolicy) Delay(attempt int) time.Duration {
	delay := math.Min(p.BaseDelay*math.Pow(p.BackoffMultiplier, float64(attempt)), p.MaxDelay)
	if p.Jitter {
		// +/- 50% jitter
		delay = delay * (0.5 + rand.Float64()) // rand in [0,1) -> [0.5, 1.5)
	}
	return time.Duration(delay * float64(time.Second))
}

// Retry executes fn with the configured retry policy.
// Only retryable errors are retried.
func Retry[T any](ctx context.Context, policy RetryPolicy, fn func(ctx context.Context) (T, error)) (T, error) {
	var zero T
	result, err := fn(ctx)
	if err == nil {
		return result, nil
	}

	for attempt := 0; attempt < policy.MaxRetries; attempt++ {
		if !IsRetryable(err) {
			return zero, err
		}

		// Check for Retry-After on rate limit errors.
		delay := policy.Delay(attempt)
		if rl, ok := err.(*RateLimitError); ok && rl.RetryAfter != nil {
			retryDelay := time.Duration(*rl.RetryAfter * float64(time.Second))
			if retryDelay > time.Duration(policy.MaxDelay*float64(time.Second)) {
				// Retry-After exceeds max_delay; raise immediately.
				return zero, err
			}
			delay = retryDelay
		}

		if policy.OnRetry != nil {
			policy.OnRetry(err, attempt+1, delay)
		}

		select {
		case <-ctx.Done():
			return zero, &AbortError{SDKError: SDKError{Message: "request cancelled during retry", Cause: ctx.Err()}}
		case <-time.After(delay):
		}

		result, err = fn(ctx)
		if err == nil {
			return result, nil
		}
	}

	return zero, err
}
