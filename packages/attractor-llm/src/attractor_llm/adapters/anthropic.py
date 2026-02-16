"""Anthropic provider adapter."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from attractor_llm.adapters.base import ProviderAdapter
from attractor_llm.errors import SDKError, error_from_status_code
from attractor_llm.request import Request
from attractor_llm.response import (
    FinishReason,
    Response,
    StreamEvent,
    StreamEventType,
    ToolCall,
    Usage,
)
from attractor_llm.sse import parse_sse_events
from attractor_llm.types import ContentKind, ContentPart, Message, Role, ThinkingData, ToolCallData


class AnthropicAdapter(ProviderAdapter):
    """Adapter for Anthropic's /v1/messages API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 60.0,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

    @property
    def name(self) -> str:
        return "anthropic"

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _build_headers(self, request: Request) -> dict[str, str]:
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        options = (request.provider_options or {}).get("anthropic")
        if isinstance(options, dict):
            beta_headers = options.get("beta_headers")
            if isinstance(beta_headers, list) and beta_headers:
                values = [str(value) for value in beta_headers if value]
                if values:
                    headers["anthropic-beta"] = ",".join(values)

        return headers

    def _build_payload(self, request: Request, *, stream: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": self._translate_messages(request.messages),
            "max_tokens": request.max_tokens or 4096,
        }

        system = self._extract_system(request.messages)
        if system:
            payload["system"] = system

        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.stop_sequences:
            payload["stop_sequences"] = request.stop_sequences
        if request.metadata:
            payload["metadata"] = request.metadata

        if not (request.tool_choice and request.tool_choice.mode == "none"):
            if request.tools:
                payload["tools"] = [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.parameters,
                    }
                    for tool in request.tools
                ]

            tool_choice = self._translate_tool_choice(request)
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice

        if stream:
            payload["stream"] = True

        return payload

    def _extract_system(self, messages: list[Message]) -> list[dict[str, str]]:
        system_blocks: list[dict[str, str]] = []

        for message in messages:
            if message.role not in (Role.SYSTEM, Role.DEVELOPER):
                continue

            for part in message.content:
                if part.kind == ContentKind.TEXT and part.text is not None:
                    system_blocks.append({"type": "text", "text": part.text})

        return system_blocks

    def _translate_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        translated: list[dict[str, Any]] = []

        for message in messages:
            if message.role in (Role.SYSTEM, Role.DEVELOPER):
                continue

            role = "assistant" if message.role == Role.ASSISTANT else "user"
            content = self._translate_content(message)
            if not content:
                continue

            if translated and translated[-1]["role"] == role:
                translated[-1]["content"].extend(content)
            else:
                translated.append({"role": role, "content": content})

        return translated

    def _translate_content(self, message: Message) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []

        for part in message.content:
            if part.kind == ContentKind.TEXT and part.text is not None:
                blocks.append({"type": "text", "text": part.text})

            elif part.kind == ContentKind.TOOL_CALL and part.tool_call is not None:
                tool_call = part.tool_call
                args: dict[str, Any]
                if isinstance(tool_call.arguments, dict):
                    args = tool_call.arguments
                elif isinstance(tool_call.arguments, str):
                    try:
                        parsed = json.loads(tool_call.arguments)
                        args = parsed if isinstance(parsed, dict) else {}
                    except json.JSONDecodeError:
                        args = {}
                else:
                    args = {}

                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tool_call.id,
                        "name": tool_call.name,
                        "input": args,
                    }
                )

            elif part.kind == ContentKind.TOOL_RESULT and part.tool_result is not None:
                result = part.tool_result
                blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": result.tool_call_id,
                        "content": result.content,
                        "is_error": result.is_error,
                    }
                )

        return blocks

    def _translate_tool_choice(self, request: Request) -> dict[str, str] | None:
        if request.tool_choice is None:
            return None

        mode = request.tool_choice.mode
        if mode == "auto":
            return {"type": "auto"}
        if mode == "required":
            return {"type": "any"}
        if mode == "named" and request.tool_choice.tool_name:
            return {"type": "tool", "name": request.tool_choice.tool_name}
        return None

    async def complete(self, request: Request) -> Response:
        response = await self._client.post(
            f"{self._base_url}/v1/messages",
            json=self._build_payload(request),
            headers=self._build_headers(request),
        )

        if response.status_code >= 400:
            raise self._error_from_response(response)

        raw = response.json()
        return self._parse_response(raw)

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        block_types: dict[int, str] = {}
        tool_states: dict[int, dict[str, Any]] = {}
        usage_input_tokens = 0
        usage_output_tokens = 0
        finish_reason_raw: str | None = None

        async with self._client.stream(
            "POST",
            f"{self._base_url}/v1/messages",
            json=self._build_payload(request, stream=True),
            headers=self._build_headers(request),
        ) as response:
            if response.status_code >= 400:
                raise self._error_from_response(response)

            async for _, data in parse_sse_events(response.aiter_lines()):
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type")

                if event_type == "message_start":
                    usage = event.get("message", {}).get("usage", {})
                    usage_input_tokens = int(usage.get("input_tokens", 0) or 0)
                    usage_output_tokens = int(usage.get("output_tokens", 0) or 0)

                elif event_type == "content_block_start":
                    index = int(event.get("index", -1))
                    block = event.get("content_block", {})
                    block_type = block.get("type", "")
                    block_types[index] = block_type

                    if block_type == "text":
                        yield StreamEvent(type=StreamEventType.TEXT_START, text_id=str(index))
                    elif block_type in ("thinking", "redacted_thinking"):
                        yield StreamEvent(type=StreamEventType.REASONING_START)
                    elif block_type == "tool_use":
                        tool_states[index] = {
                            "id": block.get("id", ""),
                            "name": block.get("name", ""),
                            "input": block.get("input")
                            if isinstance(block.get("input"), dict)
                            else {},
                            "partials": [],
                        }
                        yield StreamEvent(
                            type=StreamEventType.TOOL_CALL_START,
                            tool_call=ToolCall(
                                id=tool_states[index]["id"],
                                name=tool_states[index]["name"],
                                arguments=tool_states[index]["input"],
                            ),
                        )

                elif event_type == "content_block_delta":
                    index = int(event.get("index", -1))
                    delta = event.get("delta", {})
                    delta_type = delta.get("type")

                    if delta_type == "text_delta":
                        yield StreamEvent(
                            type=StreamEventType.TEXT_DELTA,
                            delta=delta.get("text", ""),
                            text_id=str(index),
                        )
                    elif delta_type == "thinking_delta":
                        yield StreamEvent(
                            type=StreamEventType.REASONING_DELTA,
                            reasoning_delta=delta.get("thinking", ""),
                        )
                    elif delta_type == "input_json_delta":
                        partial = delta.get("partial_json", "")
                        if index in tool_states:
                            tool_states[index]["partials"].append(partial)
                            yield StreamEvent(
                                type=StreamEventType.TOOL_CALL_DELTA,
                                tool_call=ToolCall(
                                    id=tool_states[index]["id"],
                                    name=tool_states[index]["name"],
                                    arguments={},
                                    raw_arguments=partial,
                                ),
                            )

                elif event_type == "content_block_stop":
                    index = int(event.get("index", -1))
                    block_type = block_types.get(index)
                    if block_type == "text":
                        yield StreamEvent(type=StreamEventType.TEXT_END, text_id=str(index))
                    elif block_type in ("thinking", "redacted_thinking"):
                        yield StreamEvent(type=StreamEventType.REASONING_END)
                    elif block_type == "tool_use" and index in tool_states:
                        state = tool_states[index]
                        arguments = dict(state["input"])
                        if state["partials"]:
                            combined = "".join(state["partials"])
                            try:
                                parsed = json.loads(combined)
                                if isinstance(parsed, dict):
                                    arguments.update(parsed)
                            except json.JSONDecodeError:
                                pass

                        yield StreamEvent(
                            type=StreamEventType.TOOL_CALL_END,
                            tool_call=ToolCall(
                                id=state["id"],
                                name=state["name"],
                                arguments=arguments,
                                raw_arguments="".join(state["partials"])
                                if state["partials"]
                                else None,
                            ),
                        )

                elif event_type == "message_delta":
                    delta = event.get("delta", {})
                    finish_reason_raw = delta.get("stop_reason")
                    usage = event.get("usage", {})
                    if "output_tokens" in usage:
                        usage_output_tokens = int(usage.get("output_tokens", 0) or 0)

                elif event_type == "message_stop":
                    yield StreamEvent(
                        type=StreamEventType.FINISH,
                        finish_reason=self._map_finish_reason(finish_reason_raw),
                        usage=Usage(
                            input_tokens=usage_input_tokens,
                            output_tokens=usage_output_tokens,
                        ),
                    )

    def _error_from_response(self, response: httpx.Response) -> SDKError:
        retry_after: float | None = None
        header = response.headers.get("retry-after")
        if header is not None:
            try:
                retry_after = float(header)
            except ValueError:
                retry_after = None

        raw: dict[str, Any]
        try:
            raw = response.json()
        except ValueError:
            raw = {"body": response.text}

        message = "Anthropic API error"
        if isinstance(raw, dict):
            error = raw.get("error")
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                message = error["message"]
            elif isinstance(raw.get("message"), str):
                message = raw["message"]

        return error_from_status_code(
            status_code=response.status_code,
            message=message,
            provider=self.name,
            retry_after=retry_after,
            raw=raw,
        )

    def _parse_response(self, raw: dict[str, Any]) -> Response:
        content_parts: list[ContentPart] = []
        for block in raw.get("content", []):
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")

            if block_type == "text":
                content_parts.append(ContentPart.text(block.get("text", "")))
            elif block_type == "tool_use":
                content_parts.append(
                    ContentPart.tool_call(
                        ToolCallData(
                            id=block.get("id", ""),
                            name=block.get("name", ""),
                            arguments=block.get("input")
                            if isinstance(block.get("input"), dict)
                            else {},
                        )
                    )
                )
            elif block_type == "thinking":
                content_parts.append(
                    ContentPart.thinking(
                        ThinkingData(
                            text=block.get("thinking", ""),
                            signature=block.get("signature"),
                        )
                    )
                )
            elif block_type == "redacted_thinking":
                content_parts.append(
                    ContentPart.redacted_thinking(
                        ThinkingData(
                            text=block.get("data", ""),
                            redacted=True,
                        )
                    )
                )

        usage_data = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
        usage = Usage(
            input_tokens=int(usage_data.get("input_tokens", 0) or 0),
            output_tokens=int(usage_data.get("output_tokens", 0) or 0),
            cache_read_tokens=int(usage_data["cache_read_input_tokens"])
            if usage_data.get("cache_read_input_tokens") is not None
            else None,
            cache_write_tokens=int(usage_data["cache_creation_input_tokens"])
            if usage_data.get("cache_creation_input_tokens") is not None
            else None,
            raw=usage_data,
        )

        return Response(
            id=raw.get("id", ""),
            model=raw.get("model", ""),
            provider=self.name,
            message=Message(role=Role.ASSISTANT, content=content_parts),
            finish_reason=self._map_finish_reason(raw.get("stop_reason")),
            usage=usage,
            raw=raw,
        )

    def _map_finish_reason(self, raw_reason: str | None) -> FinishReason:
        mapping = {
            "end_turn": "stop",
            "stop_sequence": "stop",
            "max_tokens": "length",
            "tool_use": "tool_calls",
        }
        return FinishReason(reason=mapping.get(raw_reason, "other"), raw=raw_reason)
