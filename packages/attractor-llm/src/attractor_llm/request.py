"""Request types: Request, ToolDefinition, ToolChoice, ResponseFormat."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from attractor_llm.types import Message


@dataclass(frozen=True)
class ToolDefinition:
    """Definition of a tool the model can call."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolChoice:
    """Controls whether and how the model calls tools."""

    mode: str  # "auto", "none", "required", "named"
    tool_name: str | None = None


@dataclass(frozen=True)
class ResponseFormat:
    """Desired response format."""

    type: str  # "text", "json", "json_schema"
    json_schema: dict[str, Any] | None = None
    strict: bool = False


@dataclass
class Request:
    """An LLM completion request."""

    model: str
    messages: list[Message]
    provider: str | None = None
    tools: list[ToolDefinition] | None = None
    tool_choice: ToolChoice | None = None
    response_format: ResponseFormat | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stop_sequences: list[str] | None = None
    reasoning_effort: str | None = None
    metadata: dict[str, str] | None = None
    provider_options: dict[str, Any] | None = None
