"""Tests for the error hierarchy and error_from_status_code."""

import pytest

from attractor_llm.errors import (
    AbortError,
    AccessDeniedError,
    AuthenticationError,
    ConfigurationError,
    ContentFilterError,
    ContextLengthError,
    InvalidRequestError,
    InvalidToolCallError,
    NetworkError,
    NoObjectGeneratedError,
    NotFoundError,
    ProviderError,
    QuotaExceededError,
    RateLimitError,
    RequestTimeoutError,
    SDKError,
    ServerError,
    StreamError,
    error_from_status_code,
)


class TestSDKError:
    def test_basic(self):
        err = SDKError("something broke")
        assert str(err) == "something broke"
        assert err.cause is None

    def test_with_cause(self):
        cause = ValueError("bad value")
        err = SDKError("wrapper", cause=cause)
        assert err.cause is cause

    def test_is_exception(self):
        err = SDKError("test")
        assert isinstance(err, Exception)


class TestProviderError:
    def test_basic(self):
        err = ProviderError(
            "bad request",
            provider="openai",
            status_code=400,
        )
        assert err.provider == "openai"
        assert err.status_code == 400
        assert err.retryable is False
        assert err.retry_after is None

    def test_retryable(self):
        err = RateLimitError(
            "rate limited",
            provider="anthropic",
            status_code=429,
            retry_after=5.0,
        )
        assert err.retryable is True
        assert err.retry_after == 5.0

    def test_inheritance(self):
        err = AuthenticationError("bad key", provider="openai", status_code=401)
        assert isinstance(err, ProviderError)
        assert isinstance(err, SDKError)
        assert isinstance(err, Exception)

    def test_raw_field(self):
        err = ProviderError(
            "error",
            provider="gemini",
            raw={"error": {"message": "details"}},
        )
        assert err.raw["error"]["message"] == "details"


class TestErrorRetryable:
    """Verify retryable flags for each error type."""

    def test_authentication_not_retryable(self):
        assert AuthenticationError("x", provider="p", status_code=401).retryable is False

    def test_access_denied_not_retryable(self):
        assert AccessDeniedError("x", provider="p", status_code=403).retryable is False

    def test_not_found_not_retryable(self):
        assert NotFoundError("x", provider="p", status_code=404).retryable is False

    def test_invalid_request_not_retryable(self):
        assert InvalidRequestError("x", provider="p", status_code=400).retryable is False

    def test_rate_limit_retryable(self):
        assert RateLimitError("x", provider="p", status_code=429).retryable is True

    def test_server_error_retryable(self):
        assert ServerError("x", provider="p", status_code=500).retryable is True

    def test_content_filter_not_retryable(self):
        assert ContentFilterError("x", provider="p").retryable is False

    def test_context_length_not_retryable(self):
        assert ContextLengthError("x", provider="p", status_code=413).retryable is False

    def test_quota_exceeded_not_retryable(self):
        assert QuotaExceededError("x", provider="p").retryable is False


class TestNonProviderErrors:
    def test_request_timeout_retryable(self):
        err = RequestTimeoutError("timeout")
        assert err.retryable is True
        assert isinstance(err, SDKError)

    def test_abort_not_retryable(self):
        err = AbortError("cancelled")
        assert err.retryable is False

    def test_network_error_retryable(self):
        err = NetworkError("connection reset")
        assert err.retryable is True

    def test_stream_error_retryable(self):
        err = StreamError("stream interrupted")
        assert err.retryable is True

    def test_invalid_tool_call_not_retryable(self):
        err = InvalidToolCallError("bad args")
        assert err.retryable is False

    def test_no_object_generated_not_retryable(self):
        err = NoObjectGeneratedError("parse failed")
        assert err.retryable is False

    def test_configuration_error_not_retryable(self):
        err = ConfigurationError("missing key")
        assert err.retryable is False


class TestErrorFromStatusCode:
    @pytest.mark.parametrize(
        "status,expected_type",
        [
            (400, InvalidRequestError),
            (401, AuthenticationError),
            (403, AccessDeniedError),
            (404, NotFoundError),
            (408, RequestTimeoutError),
            (413, ContextLengthError),
            (422, InvalidRequestError),
            (429, RateLimitError),
            (500, ServerError),
            (502, ServerError),
            (503, ServerError),
            (504, ServerError),
        ],
    )
    def test_status_code_mapping(self, status, expected_type):
        err = error_from_status_code(
            status_code=status,
            message=f"Error {status}",
            provider="test",
        )
        assert isinstance(err, expected_type)

    def test_message_classification_not_found(self):
        err = error_from_status_code(
            status_code=499,
            message="The model does not exist",
            provider="test",
        )
        assert isinstance(err, NotFoundError)

    def test_message_classification_auth(self):
        err = error_from_status_code(
            status_code=499,
            message="Unauthorized: invalid key provided",
            provider="test",
        )
        assert isinstance(err, AuthenticationError)

    def test_message_classification_context_length(self):
        err = error_from_status_code(
            status_code=499,
            message="context length exceeded, too many tokens",
            provider="test",
        )
        assert isinstance(err, ContextLengthError)

    def test_message_classification_content_filter(self):
        err = error_from_status_code(
            status_code=499,
            message="content filter triggered for safety",
            provider="test",
        )
        assert isinstance(err, ContentFilterError)

    def test_unknown_status_defaults_to_server_error(self):
        """Unknown errors default to retryable ServerError."""
        err = error_from_status_code(
            status_code=599,
            message="Something weird happened",
            provider="test",
        )
        assert isinstance(err, ServerError)
        assert err.retryable is True

    def test_retry_after_passed_through(self):
        err = error_from_status_code(
            status_code=429,
            message="rate limited",
            provider="anthropic",
            retry_after=30.0,
        )
        assert err.retry_after == 30.0
