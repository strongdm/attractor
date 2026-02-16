"""Tests for RetryPolicy and retry helper."""

import asyncio

import pytest

from attractor_llm.errors import (
    AuthenticationError,
    RateLimitError,
    SDKError,
    ServerError,
)
from attractor_llm.retry import RetryPolicy, delay_for_attempt, retry


class TestDelayForAttempt:
    def test_exponential_growth(self):
        policy = RetryPolicy(base_delay=1.0, backoff_multiplier=2.0, jitter=False)
        assert delay_for_attempt(0, policy) == 1.0
        assert delay_for_attempt(1, policy) == 2.0
        assert delay_for_attempt(2, policy) == 4.0
        assert delay_for_attempt(3, policy) == 8.0

    def test_max_delay_cap(self):
        policy = RetryPolicy(
            base_delay=1.0, backoff_multiplier=2.0, max_delay=5.0, jitter=False
        )
        assert delay_for_attempt(0, policy) == 1.0
        assert delay_for_attempt(1, policy) == 2.0
        assert delay_for_attempt(2, policy) == 4.0
        assert delay_for_attempt(3, policy) == 5.0  # capped
        assert delay_for_attempt(10, policy) == 5.0  # still capped

    def test_jitter_within_range(self):
        policy = RetryPolicy(base_delay=10.0, backoff_multiplier=1.0, jitter=True)
        delays = [delay_for_attempt(0, policy) for _ in range(100)]
        assert all(5.0 <= d <= 15.0 for d in delays), f"Delays out of range: {min(delays)}-{max(delays)}"
        # Should have some variance
        assert min(delays) < max(delays)


class TestRetryPolicy:
    def test_defaults(self):
        policy = RetryPolicy()
        assert policy.max_retries == 2
        assert policy.base_delay == 1.0
        assert policy.max_delay == 60.0
        assert policy.backoff_multiplier == 2.0
        assert policy.jitter is True

    def test_custom(self):
        policy = RetryPolicy(max_retries=5, base_delay=0.5)
        assert policy.max_retries == 5
        assert policy.base_delay == 0.5

    def test_disabled(self):
        policy = RetryPolicy(max_retries=0)
        assert policy.max_retries == 0


class TestRetryHelper:
    async def test_success_no_retry(self):
        call_count = 0

        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await retry(succeed, RetryPolicy(max_retries=3))
        assert result == "ok"
        assert call_count == 1

    async def test_retries_on_retryable_error(self):
        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ServerError("server down", provider="test", status_code=500)
            return "recovered"

        policy = RetryPolicy(max_retries=3, base_delay=0.01, jitter=False)
        result = await retry(fail_then_succeed, policy)
        assert result == "recovered"
        assert call_count == 3

    async def test_no_retry_on_non_retryable(self):
        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise AuthenticationError("bad key", provider="test", status_code=401)

        policy = RetryPolicy(max_retries=3, base_delay=0.01)
        with pytest.raises(AuthenticationError):
            await retry(always_fail, policy)
        assert call_count == 1  # No retries for non-retryable

    async def test_exhaustion_raises_last_error(self):
        async def always_fail():
            raise ServerError("still down", provider="test", status_code=500)

        policy = RetryPolicy(max_retries=2, base_delay=0.01, jitter=False)
        with pytest.raises(ServerError, match="still down"):
            await retry(always_fail, policy)

    async def test_zero_retries_no_retry(self):
        call_count = 0

        async def fail():
            nonlocal call_count
            call_count += 1
            raise ServerError("error", provider="test", status_code=500)

        policy = RetryPolicy(max_retries=0)
        with pytest.raises(ServerError):
            await retry(fail, policy)
        assert call_count == 1

    async def test_on_retry_callback(self):
        callback_calls = []

        def on_retry(error, attempt, delay):
            callback_calls.append((str(error), attempt, delay))

        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ServerError("error", provider="test", status_code=500)
            return "ok"

        policy = RetryPolicy(max_retries=3, base_delay=0.01, jitter=False, on_retry=on_retry)
        await retry(fail_then_succeed, policy)
        assert len(callback_calls) == 1
        assert callback_calls[0][1] == 1  # attempt number

    async def test_retry_after_overrides_backoff(self):
        """When error has retry_after, use that instead of calculated delay."""
        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RateLimitError(
                    "rate limited",
                    provider="test",
                    status_code=429,
                    retry_after=0.01,
                )
            return "ok"

        policy = RetryPolicy(max_retries=2, base_delay=100.0, jitter=False)
        result = await retry(fail_then_succeed, policy)
        assert result == "ok"

    async def test_retry_after_exceeds_max_raises_immediately(self):
        """When retry_after > max_delay, raise immediately without retrying."""
        async def always_rate_limited():
            raise RateLimitError(
                "rate limited",
                provider="test",
                status_code=429,
                retry_after=999.0,
            )

        policy = RetryPolicy(max_retries=3, max_delay=60.0, base_delay=0.01)
        with pytest.raises(RateLimitError):
            await retry(always_rate_limited, policy)

    async def test_non_sdk_error_not_retried(self):
        """Non-SDKError exceptions should not be retried."""
        call_count = 0

        async def raise_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("not an SDK error")

        policy = RetryPolicy(max_retries=3, base_delay=0.01)
        with pytest.raises(ValueError):
            await retry(raise_value_error, policy)
        assert call_count == 1
