"""Error hierarchy for the unified LLM client."""

from __future__ import annotations

from typing import Any


class SDKError(Exception):
    """Base error for all SDK errors."""

    def __init__(self, message: str, *, cause: Exception | None = None):
        super().__init__(message)
        self.cause = cause


# --- Provider errors (from HTTP responses) ---


class ProviderError(SDKError):
    """Error returned by a provider's API."""

    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status_code: int | None = None,
        error_code: str | None = None,
        retry_after: float | None = None,
        raw: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, cause=cause)
        self.provider = provider
        self.status_code = status_code
        self.error_code = error_code
        self.retry_after = retry_after
        self.raw = raw


class AuthenticationError(ProviderError):
    """401 - Invalid API key or credentials."""

    retryable = False


class AccessDeniedError(ProviderError):
    """403 - Permission denied."""

    retryable = False


class NotFoundError(ProviderError):
    """404 - Resource (model, endpoint) not found."""

    retryable = False


class InvalidRequestError(ProviderError):
    """400/422 - Malformed request."""

    retryable = False


class RateLimitError(ProviderError):
    """429 - Rate limit exceeded."""

    retryable = True


class ServerError(ProviderError):
    """500-599 - Provider server error."""

    retryable = True


class ContentFilterError(ProviderError):
    """Response blocked by safety filter."""

    retryable = False


class ContextLengthError(ProviderError):
    """413 - Input too long for model's context window."""

    retryable = False


class QuotaExceededError(ProviderError):
    """Usage quota exhausted."""

    retryable = False


# --- Non-provider errors ---


class _RetryableSDKError(SDKError):
    retryable: bool = True


class _NonRetryableSDKError(SDKError):
    retryable: bool = False


class RequestTimeoutError(_RetryableSDKError):
    """408 - Request timed out."""


class AbortError(_NonRetryableSDKError):
    """Operation was cancelled."""


class NetworkError(_RetryableSDKError):
    """Network connectivity issue."""


class StreamError(_RetryableSDKError):
    """Error during streaming."""


class InvalidToolCallError(_NonRetryableSDKError):
    """Model produced an invalid tool call."""


class NoObjectGeneratedError(_NonRetryableSDKError):
    """Structured output could not be parsed/validated."""


class ConfigurationError(_NonRetryableSDKError):
    """SDK misconfiguration."""


# --- Factory ---

_STATUS_MAP: dict[int, type[ProviderError | RequestTimeoutError]] = {
    400: InvalidRequestError,
    401: AuthenticationError,
    403: AccessDeniedError,
    404: NotFoundError,
    408: RequestTimeoutError,
    413: ContextLengthError,
    422: InvalidRequestError,
    429: RateLimitError,
    500: ServerError,
    502: ServerError,
    503: ServerError,
    504: ServerError,
}

_MESSAGE_PATTERNS: list[tuple[list[str], type[ProviderError]]] = [
    (["not found", "does not exist"], NotFoundError),
    (["unauthorized", "invalid key"], AuthenticationError),
    (["context length", "too many tokens"], ContextLengthError),
    (["content filter", "safety"], ContentFilterError),
]


def error_from_status_code(
    *,
    status_code: int,
    message: str,
    provider: str,
    retry_after: float | None = None,
    raw: dict[str, Any] | None = None,
) -> SDKError:
    """Create the appropriate error type from an HTTP status code and message."""
    error_cls = _STATUS_MAP.get(status_code)

    # Message-based classification for unmapped status codes
    if error_cls is None:
        msg_lower = message.lower()
        for patterns, cls in _MESSAGE_PATTERNS:
            if any(p in msg_lower for p in patterns):
                error_cls = cls
                break

    # Default to ServerError (retryable) for unknown errors
    if error_cls is None:
        error_cls = ServerError

    if error_cls is RequestTimeoutError:
        return RequestTimeoutError(message)

    return error_cls(
        message,
        provider=provider,
        status_code=status_code,
        retry_after=retry_after,
        raw=raw,
    )
