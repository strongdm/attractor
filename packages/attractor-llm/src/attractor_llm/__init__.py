"""Unified multi-provider LLM client."""

from attractor_llm.adapters import (
    AnthropicAdapter,
    GeminiAdapter,
    OpenAIAdapter,
    OpenAICompatAdapter,
)
from attractor_llm.client import Client, get_default_client, set_default_client
from attractor_llm.highlevel import (
    GenerateResult,
    StreamAccumulator,
    StreamResult,
    generate,
    generate_object,
    stream,
)
from attractor_llm.request import Request, ResponseFormat, ToolChoice, ToolDefinition
from attractor_llm.response import (
    FinishReason,
    Response,
    StreamEvent,
    StreamEventType,
    ToolCall,
    Usage,
)
from attractor_llm.types import ContentPart, Message, Role

__all__ = [
    "AnthropicAdapter",
    "Client",
    "ContentPart",
    "FinishReason",
    "GeminiAdapter",
    "GenerateResult",
    "Message",
    "OpenAIAdapter",
    "OpenAICompatAdapter",
    "Request",
    "Response",
    "ResponseFormat",
    "Role",
    "StreamAccumulator",
    "StreamEvent",
    "StreamEventType",
    "StreamResult",
    "ToolCall",
    "ToolChoice",
    "ToolDefinition",
    "Usage",
    "generate",
    "generate_object",
    "get_default_client",
    "set_default_client",
    "stream",
]
