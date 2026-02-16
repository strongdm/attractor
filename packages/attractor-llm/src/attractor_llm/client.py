"""Core Client: provider routing, middleware chain, and module-level default client."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, AsyncIterator, Awaitable, Callable

from attractor_llm.adapters.base import ProviderAdapter
from attractor_llm.errors import ConfigurationError
from attractor_llm.request import Request
from attractor_llm.response import Response, StreamEvent

# Middleware signature for complete(): async (request, next_fn) -> Response
# Middleware signature for stream(): async (request, next_fn) -> AsyncIterator[StreamEvent]
Middleware = Callable[..., Any]

_default_client: Client | None = None


def set_default_client(client: Client | None) -> None:
    """Set the module-level default client."""
    global _default_client
    _default_client = client


def get_default_client() -> Client | None:
    """Get the module-level default client."""
    return _default_client


class Client:
    """Routes requests to provider adapters with middleware support."""

    def __init__(
        self,
        providers: dict[str, ProviderAdapter],
        default_provider: str | None = None,
        middleware: list[Middleware] | None = None,
    ):
        self._providers = providers
        self._default_provider = default_provider
        self._middleware = middleware or []

    @classmethod
    def from_env(cls, *, environ: Mapping[str, str] | None = None) -> Client:
        """Build a client from provider API keys in the environment."""
        from attractor_llm.adapters import (
            AnthropicAdapter,
            GeminiAdapter,
            OpenAIAdapter,
            OpenAICompatAdapter,
        )

        env = environ or os.environ
        providers: dict[str, ProviderAdapter] = {}

        openai_key = env.get("OPENAI_API_KEY")
        if openai_key:
            providers["openai"] = OpenAIAdapter(api_key=openai_key)

        anthropic_key = env.get("ANTHROPIC_API_KEY")
        if anthropic_key:
            providers["anthropic"] = AnthropicAdapter(api_key=anthropic_key)

        gemini_key = env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")
        if gemini_key:
            providers["gemini"] = GeminiAdapter(api_key=gemini_key)

        openai_compat_key = env.get("OPENAI_COMPAT_API_KEY")
        if openai_compat_key:
            base_url = env.get("OPENAI_COMPAT_BASE_URL") or "https://api.openai.com"
            providers["openai_compat"] = OpenAICompatAdapter(
                api_key=openai_compat_key,
                base_url=base_url,
            )

        if not providers:
            raise ConfigurationError("No providers configured from environment")

        default_provider = next(iter(providers.keys()))
        return cls(providers=providers, default_provider=default_provider)

    def _resolve_adapter(self, request: Request) -> ProviderAdapter:
        """Resolve which adapter to use for this request."""
        if request.provider is not None:
            adapter = self._providers.get(request.provider)
            if adapter is None:
                raise ConfigurationError(
                    f"Unknown provider: {request.provider!r}. "
                    f"Available: {list(self._providers.keys())}"
                )
            return adapter

        if self._default_provider is not None:
            return self._providers[self._default_provider]

        if len(self._providers) == 1:
            return next(iter(self._providers.values()))

        raise ConfigurationError(
            "No provider specified and no default configured. "
            f"Available providers: {list(self._providers.keys())}"
        )

    async def complete(self, request: Request) -> Response:
        """Send a completion request through the middleware chain."""
        adapter = self._resolve_adapter(request)

        # Build the chain: middleware wraps the core handler
        async def core(req: Request) -> Response:
            return await adapter.complete(req)

        handler = core
        for mw in reversed(self._middleware):
            handler = _wrap_complete_middleware(mw, handler)

        return await handler(request)

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        """Send a streaming request through the middleware chain."""
        adapter = self._resolve_adapter(request)

        # Build the chain for streaming
        async def core(req: Request) -> AsyncIterator[StreamEvent]:
            async for event in adapter.stream(req):
                yield event

        handler = core
        for mw in reversed(self._middleware):
            handler = _wrap_stream_middleware(mw, handler)

        async for event in handler(request):
            yield event

    async def close(self) -> None:
        """Close all provider adapters."""
        for adapter in self._providers.values():
            await adapter.close()


def _wrap_complete_middleware(mw: Middleware, next_fn: Any) -> Any:
    """Wrap a middleware around a complete handler."""

    async def handler(request: Request) -> Response:
        return await mw(request, next_fn)

    return handler


def _wrap_stream_middleware(mw: Middleware, next_fn: Any) -> Any:
    """Wrap a middleware around a stream handler."""

    async def handler(request: Request) -> AsyncIterator[StreamEvent]:
        async for event in mw(request, next_fn):
            yield event

    return handler
