"""OpenAI Responses provider adapter."""

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
from attractor_llm.types import ContentKind, ContentPart, Message, Role, ToolCallData


class OpenAIAdapter(ProviderAdapter):
    """Adapter for OpenAI's /v1/responses API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com",
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 60.0,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

    @property
    def name(self) -> str:
        return "openai"

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _build_headers(self) -> dict[str, str]:
        return {
            "authorization": f"Bearer {self._api_key}",
            "content-type": "application/json",
        }

    def _build_payload(self, request: Request, *, stream: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "input": self._translate_messages(request.messages),
        }

        instructions = self._extract_instructions(request.messages)
        if instructions:
            payload["instructions"] = instructions

        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.max_tokens is not None:
            payload["max_output_tokens"] = request.max_tokens
        if request.stop_sequences:
            payload["stop"] = request.stop_sequences
        if request.metadata:
            payload["metadata"] = request.metadata

        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
                for tool in request.tools
            ]

        tool_choice = self._translate_tool_choice(request)
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        if request.reasoning_effort:
            payload["reasoning"] = {"effort": request.reasoning_effort}

        if (
            request.response_format
            and request.response_format.type == "json_schema"
            and request.response_format.json_schema is not None
        ):
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "schema": request.response_format.json_schema,
                    "strict": request.response_format.strict,
                }
            }

        if stream:
            payload["stream"] = True

        return payload

    def _extract_instructions(self, messages: list[Message]) -> str:
        parts: list[str] = []
        for message in messages:
            if message.role not in (Role.SYSTEM, Role.DEVELOPER):
                continue
            for part in message.content:
                if part.kind == ContentKind.TEXT and part.text is not None:
                    parts.append(part.text)
        return "\n\n".join(parts)

    def _translate_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []

        for message in messages:
            if message.role in (Role.SYSTEM, Role.DEVELOPER):
                continue

            role = "assistant" if message.role == Role.ASSISTANT else "user"
            text_type = "output_text" if role == "assistant" else "input_text"
            pending_content: list[dict[str, str]] = []

            for part in message.content:
                if part.kind == ContentKind.TEXT and part.text is not None:
                    pending_content.append({"type": text_type, "text": part.text})
                    continue

                if pending_content:
                    items.append({"type": "message", "role": role, "content": pending_content})
                    pending_content = []

                if part.kind == ContentKind.TOOL_CALL and part.tool_call is not None:
                    items.append(self._translate_tool_call(part.tool_call))
                elif part.kind == ContentKind.TOOL_RESULT and part.tool_result is not None:
                    items.append(
                        {
                            "type": "function_call_output",
                            "call_id": part.tool_result.tool_call_id,
                            "output": part.tool_result.content,
                        }
                    )

            if pending_content:
                items.append({"type": "message", "role": role, "content": pending_content})

        return items

    def _translate_tool_call(self, tool_call: ToolCallData) -> dict[str, Any]:
        arguments: str
        if isinstance(tool_call.arguments, dict):
            arguments = json.dumps(tool_call.arguments)
        else:
            arguments = tool_call.arguments

        return {
            "type": "function_call",
            "id": tool_call.id,
            "call_id": tool_call.id,
            "name": tool_call.name,
            "arguments": arguments,
        }

    def _translate_tool_choice(self, request: Request) -> str | dict[str, str] | None:
        if request.tool_choice is None:
            return None

        mode = request.tool_choice.mode
        if mode in ("auto", "none", "required"):
            return mode
        if mode == "named" and request.tool_choice.tool_name:
            return {"type": "function", "name": request.tool_choice.tool_name}
        return None

    async def complete(self, request: Request) -> Response:
        response = await self._client.post(
            f"{self._base_url}/v1/responses",
            json=self._build_payload(request),
            headers=self._build_headers(),
        )

        if response.status_code >= 400:
            raise self._error_from_response(response)

        raw = response.json()
        return self._parse_response(raw)

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        text_started: set[str] = set()
        tool_states: dict[int, dict[str, str]] = {}

        async with self._client.stream(
            "POST",
            f"{self._base_url}/v1/responses",
            json=self._build_payload(request, stream=True),
            headers=self._build_headers(),
        ) as response:
            if response.status_code >= 400:
                raise self._error_from_response(response)

            async for _, data in parse_sse_events(response.aiter_lines()):
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type")

                if event_type == "response.output_item.added":
                    output_index = int(event.get("output_index", -1))
                    item = event.get("item", {})
                    item_type = item.get("type")

                    if item_type == "message":
                        text_id = f"{output_index}:0"
                        text_started.add(text_id)
                        yield StreamEvent(type=StreamEventType.TEXT_START, text_id=text_id)
                    elif item_type == "function_call":
                        tool_states[output_index] = {
                            "id": str(item.get("call_id") or item.get("id") or ""),
                            "name": str(item.get("name") or ""),
                        }
                        yield StreamEvent(
                            type=StreamEventType.TOOL_CALL_START,
                            tool_call=ToolCall(
                                id=tool_states[output_index]["id"],
                                name=tool_states[output_index]["name"],
                                arguments={},
                            ),
                        )

                elif event_type == "response.output_text.delta":
                    output_index = int(event.get("output_index", -1))
                    content_index = int(event.get("content_index", 0))
                    text_id = f"{output_index}:{content_index}"
                    if text_id not in text_started:
                        text_started.add(text_id)
                        yield StreamEvent(type=StreamEventType.TEXT_START, text_id=text_id)
                    yield StreamEvent(
                        type=StreamEventType.TEXT_DELTA,
                        delta=event.get("delta", ""),
                        text_id=text_id,
                    )

                elif event_type == "response.output_text.done":
                    output_index = int(event.get("output_index", -1))
                    content_index = int(event.get("content_index", 0))
                    text_id = f"{output_index}:{content_index}"
                    yield StreamEvent(type=StreamEventType.TEXT_END, text_id=text_id)

                elif event_type == "response.function_call_arguments.delta":
                    output_index = int(event.get("output_index", -1))
                    state = tool_states.get(output_index, {"id": "", "name": ""})
                    partial = event.get("delta", "")
                    yield StreamEvent(
                        type=StreamEventType.TOOL_CALL_DELTA,
                        tool_call=ToolCall(
                            id=state["id"],
                            name=state["name"],
                            arguments={},
                            raw_arguments=partial,
                        ),
                    )

                elif event_type == "response.function_call_arguments.done":
                    output_index = int(event.get("output_index", -1))
                    state = tool_states.get(output_index, {"id": "", "name": ""})
                    raw_arguments = event.get("arguments", "")
                    arguments = self._parse_arguments(raw_arguments)
                    yield StreamEvent(
                        type=StreamEventType.TOOL_CALL_END,
                        tool_call=ToolCall(
                            id=state["id"],
                            name=state["name"],
                            arguments=arguments,
                            raw_arguments=raw_arguments,
                        ),
                    )

                elif event_type in (
                    "response.completed",
                    "response.incomplete",
                    "response.failed",
                ):
                    raw_response = event.get("response", {})
                    usage = self._parse_usage(raw_response.get("usage"))
                    yield StreamEvent(
                        type=StreamEventType.FINISH,
                        finish_reason=self._map_finish_reason(raw_response),
                        usage=usage,
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

        message = "OpenAI API error"
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
        for item in raw.get("output", []):
            if not isinstance(item, dict):
                continue

            item_type = item.get("type")
            if item_type == "message":
                for block in item.get("content", []):
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") in ("output_text", "text"):
                        content_parts.append(ContentPart.text(block.get("text", "")))
            elif item_type == "function_call":
                raw_arguments = item.get("arguments", "")
                content_parts.append(
                    ContentPart.tool_call(
                        ToolCallData(
                            id=str(item.get("call_id") or item.get("id") or ""),
                            name=str(item.get("name") or ""),
                            arguments=self._parse_arguments(raw_arguments),
                        )
                    )
                )

        return Response(
            id=raw.get("id", ""),
            model=raw.get("model", ""),
            provider=self.name,
            message=Message(role=Role.ASSISTANT, content=content_parts),
            finish_reason=self._map_finish_reason(raw),
            usage=self._parse_usage(raw.get("usage")),
            raw=raw,
        )

    def _parse_usage(self, usage: Any) -> Usage:
        usage_data = usage if isinstance(usage, dict) else {}
        output_details = (
            usage_data.get("output_tokens_details")
            if isinstance(usage_data.get("output_tokens_details"), dict)
            else {}
        )
        input_details = (
            usage_data.get("input_tokens_details")
            if isinstance(usage_data.get("input_tokens_details"), dict)
            else {}
        )

        return Usage(
            input_tokens=int(usage_data.get("input_tokens", 0) or 0),
            output_tokens=int(usage_data.get("output_tokens", 0) or 0),
            reasoning_tokens=int(output_details["reasoning_tokens"])
            if output_details.get("reasoning_tokens") is not None
            else None,
            cache_read_tokens=int(input_details["cached_tokens"])
            if input_details.get("cached_tokens") is not None
            else None,
            raw=usage_data,
        )

    def _map_finish_reason(self, raw: dict[str, Any]) -> FinishReason:
        output_items = raw.get("output", []) if isinstance(raw.get("output"), list) else []
        if any(
            isinstance(item, dict) and item.get("type") == "function_call" for item in output_items
        ):
            return FinishReason(reason="tool_calls", raw="function_call")

        status = raw.get("status")
        incomplete = raw.get("incomplete_details")
        incomplete_reason = incomplete.get("reason") if isinstance(incomplete, dict) else None

        if incomplete_reason == "max_output_tokens":
            return FinishReason(reason="length", raw=incomplete_reason)
        if incomplete_reason in ("content_filter", "safety"):
            return FinishReason(reason="content_filter", raw=incomplete_reason)
        if status == "completed":
            return FinishReason(reason="stop", raw=status)
        if status == "failed":
            return FinishReason(reason="error", raw=status)
        return FinishReason(reason="other", raw=incomplete_reason or status)

    def _parse_arguments(self, raw_arguments: Any) -> dict[str, Any]:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if not isinstance(raw_arguments, str):
            return {}
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
