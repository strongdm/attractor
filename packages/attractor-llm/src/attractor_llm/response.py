"""Response types: Response, FinishReason, Usage, StreamEvent, and supporting types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from attractor_llm.types import ContentKind, Message, ToolCallData


@dataclass(frozen=True)
class FinishReason:
    """Why generation stopped."""

    reason: str  # "stop", "length", "tool_calls", "content_filter", "error", "other"
    raw: str | None = None


@dataclass(frozen=True)
class Usage:
    """Token usage statistics."""

    input_tokens: int
    output_tokens: int
    reasoning_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    raw: dict[str, Any] | None = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: Usage) -> Usage:
        def _add_optional(a: int | None, b: int | None) -> int | None:
            if a is None and b is None:
                return None
            return (a or 0) + (b or 0)

        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            reasoning_tokens=_add_optional(self.reasoning_tokens, other.reasoning_tokens),
            cache_read_tokens=_add_optional(self.cache_read_tokens, other.cache_read_tokens),
            cache_write_tokens=_add_optional(self.cache_write_tokens, other.cache_write_tokens),
        )


@dataclass(frozen=True)
class ToolCall:
    """A parsed tool call from the model."""

    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str | None = None


@dataclass(frozen=True)
class ToolResult:
    """Result of executing a tool call."""

    tool_call_id: str
    content: str | dict[str, Any] | list
    is_error: bool = False


@dataclass(frozen=True)
class Warning:
    """A non-fatal issue in a response."""

    message: str
    code: str | None = None


@dataclass(frozen=True)
class RateLimitInfo:
    """Rate limit metadata from provider response headers."""

    requests_remaining: int | None = None
    requests_limit: int | None = None
    tokens_remaining: int | None = None
    tokens_limit: int | None = None
    reset_at: datetime | None = None


@dataclass
class Response:
    """A complete LLM response."""

    id: str
    model: str
    provider: str
    message: Message
    finish_reason: FinishReason
    usage: Usage
    raw: dict[str, Any] | None = None
    warnings: list[Warning] = field(default_factory=list)
    rate_limit: RateLimitInfo | None = None

    @property
    def text(self) -> str:
        """Concatenated text from all text parts."""
        return self.message.text

    @property
    def tool_calls(self) -> list[ToolCall]:
        """Extract tool calls from the response message."""
        result = []
        for part in self.message.content:
            if part.kind == ContentKind.TOOL_CALL and part.tool_call is not None:
                tc = part.tool_call
                args = tc.arguments if isinstance(tc.arguments, dict) else {}
                result.append(ToolCall(
                    id=tc.id,
                    name=tc.name,
                    arguments=args,
                ))
        return result

    @property
    def reasoning(self) -> str | None:
        """Concatenated reasoning/thinking text, or None if no thinking blocks."""
        parts = []
        for part in self.message.content:
            if part.kind == ContentKind.THINKING and part.thinking is not None:
                parts.append(part.thinking.text)
        return "".join(parts) if parts else None


class StreamEventType(Enum):
    """Types of streaming events."""

    STREAM_START = "stream_start"
    TEXT_START = "text_start"
    TEXT_DELTA = "text_delta"
    TEXT_END = "text_end"
    REASONING_START = "reasoning_start"
    REASONING_DELTA = "reasoning_delta"
    REASONING_END = "reasoning_end"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_END = "tool_call_end"
    FINISH = "finish"
    ERROR = "error"
    PROVIDER_EVENT = "provider_event"


@dataclass
class StreamEvent:
    """A single event in an LLM streaming response."""

    type: StreamEventType

    # Text events
    delta: str | None = None
    text_id: str | None = None

    # Reasoning events
    reasoning_delta: str | None = None

    # Tool call events
    tool_call: ToolCall | None = None

    # Finish event
    finish_reason: FinishReason | None = None
    usage: Usage | None = None
    response: Response | None = None

    # Error event
    error: Exception | None = None

    # Passthrough
    raw: dict[str, Any] | None = None
