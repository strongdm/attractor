package unifiedllm

import "fmt"

// SDKError is the base error type for all unified LLM errors.
type SDKError struct {
	Message string
	Cause   error
}

func (e *SDKError) Error() string {
	if e.Cause != nil {
		return fmt.Sprintf("%s: %v", e.Message, e.Cause)
	}
	return e.Message
}

func (e *SDKError) Unwrap() error {
	return e.Cause
}

// ProviderError represents an error returned by an LLM provider.
type ProviderError struct {
	SDKError
	Provider   string
	StatusCode int
	ErrorCode  string
	Retryable  bool
	RetryAfter *float64
	Raw        map[string]interface{}
}

func (e *ProviderError) Error() string {
	return fmt.Sprintf("[%s] %s (status=%d, retryable=%v)", e.Provider, e.Message, e.StatusCode, e.Retryable)
}

// Concrete provider error types.

type AuthenticationError struct{ ProviderError }
type AccessDeniedError struct{ ProviderError }
type NotFoundError struct{ ProviderError }
type InvalidRequestError struct{ ProviderError }
type RateLimitError struct{ ProviderError }
type ServerError struct{ ProviderError }
type ContentFilterError struct{ ProviderError }
type ContextLengthError struct{ ProviderError }
type QuotaExceededError struct{ ProviderError }

// Non-provider errors.

type RequestTimeoutError struct{ SDKError }
type AbortError struct{ SDKError }
type NetworkError struct{ SDKError }
type StreamErrorType struct{ SDKError }
type InvalidToolCallError struct{ SDKError }
type NoObjectGeneratedError struct{ SDKError }
type ConfigurationError struct{ SDKError }

// ErrorFromStatusCode maps an HTTP status code to the appropriate error type.
func ErrorFromStatusCode(statusCode int, message, provider, errorCode string, raw map[string]interface{}, retryAfter *float64) error {
	pe := ProviderError{
		SDKError:   SDKError{Message: message},
		Provider:   provider,
		StatusCode: statusCode,
		ErrorCode:  errorCode,
		Raw:        raw,
		RetryAfter: retryAfter,
	}

	switch statusCode {
	case 400, 422:
		pe.Retryable = false
		return &InvalidRequestError{ProviderError: pe}
	case 401:
		pe.Retryable = false
		return &AuthenticationError{ProviderError: pe}
	case 403:
		pe.Retryable = false
		return &AccessDeniedError{ProviderError: pe}
	case 404:
		pe.Retryable = false
		return &NotFoundError{ProviderError: pe}
	case 408:
		pe.Retryable = true
		return &RequestTimeoutError{SDKError: SDKError{Message: message}}
	case 413:
		pe.Retryable = false
		return &ContextLengthError{ProviderError: pe}
	case 429:
		pe.Retryable = true
		return &RateLimitError{ProviderError: pe}
	case 500, 502, 503, 504:
		pe.Retryable = true
		return &ServerError{ProviderError: pe}
	default:
		// Unknown errors default to retryable.
		pe.Retryable = true
		return &pe
	}
}

// IsRetryable returns true if the error is safe to retry.
func IsRetryable(err error) bool {
	if err == nil {
		return false
	}
	switch e := err.(type) {
	case *ProviderError:
		return e.Retryable
	case *AuthenticationError:
		return false
	case *AccessDeniedError:
		return false
	case *NotFoundError:
		return false
	case *InvalidRequestError:
		return false
	case *ContextLengthError:
		return false
	case *QuotaExceededError:
		return false
	case *ContentFilterError:
		return false
	case *ConfigurationError:
		return false
	case *RateLimitError:
		return true
	case *ServerError:
		return true
	case *NetworkError:
		return true
	case *StreamErrorType:
		return true
	case *RequestTimeoutError:
		return true
	default:
		// Unknown errors default to retryable.
		return true
	}
}
