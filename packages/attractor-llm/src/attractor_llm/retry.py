"""Retry policy with exponential backoff and jitter."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypeVar

from attractor_llm.errors import SDKError

T = TypeVar("T")


@dataclass
class RetryPolicy:
    """Configuration for automatic retries."""

    max_retries: int = 2
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_multiplier: float = 2.0
    jitter: bool = True
    on_retry: Callable[[Exception, int, float], None] | None = None


def delay_for_attempt(attempt: int, policy: RetryPolicy) -> float:
    """Calculate delay for a given retry attempt (0-indexed)."""
    delay = min(
        policy.base_delay * (policy.backoff_multiplier ** attempt),
        policy.max_delay,
    )
    if policy.jitter:
        delay = delay * random.uniform(0.5, 1.5)
    return delay


async def retry(
    fn: Callable[[], Awaitable[T]],
    policy: RetryPolicy,
) -> T:
    """Execute fn with retry logic per the policy.

    Only retries on SDKError subclasses with retryable=True.
    Non-SDKError exceptions and non-retryable SDKErrors are raised immediately.
    """
    last_error: Exception | None = None

    for attempt in range(policy.max_retries + 1):
        try:
            return await fn()
        except SDKError as e:
            last_error = e

            if not getattr(e, "retryable", False):
                raise

            if attempt >= policy.max_retries:
                raise

            # Check retry_after from provider
            retry_after = getattr(e, "retry_after", None)
            if retry_after is not None and retry_after > policy.max_delay:
                raise

            if retry_after is not None:
                wait = retry_after
            else:
                wait = delay_for_attempt(attempt, policy)

            if policy.on_retry is not None:
                policy.on_retry(e, attempt + 1, wait)

            await asyncio.sleep(wait)
        except Exception:
            raise

    # Should never reach here, but satisfy type checker
    assert last_error is not None
    raise last_error
