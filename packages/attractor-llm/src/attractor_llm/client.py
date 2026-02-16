"""Core Client: provider routing, middleware chain, and module-level default client."""

from __future__ import annotations

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
