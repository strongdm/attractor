"""ProviderAdapter abstract base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from attractor_llm.request import Request
from attractor_llm.response import Response, StreamEvent


class ProviderAdapter(ABC):
    """Interface that every provider adapter must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g., 'openai', 'anthropic', 'gemini')."""
        ...

    @abstractmethod
    async def complete(self, request: Request) -> Response:
        """Send request, block until model finishes, return full response."""
        ...

    @abstractmethod
    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        """Send request, return async iterator of stream events."""
        ...
        # Make this an async generator to satisfy type checker
        if False:  # pragma: no cover
            yield  # type: ignore

    async def close(self) -> None:
        """Release resources (HTTP connections, etc.)."""

    async def initialize(self) -> None:
        """Validate configuration on startup."""

    def supports_tool_choice(self, mode: str) -> bool:
        """Query whether a particular tool_choice mode is supported."""
        return True
