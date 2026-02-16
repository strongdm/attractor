"""OpenAI-compatible Chat Completions provider adapter."""

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


class OpenAICompatAdapter(ProviderAdapter):
    """Adapter for OpenAI-compatible /v1/chat/completions APIs."""

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
        return "openai_compat"

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
            "messages": self._translate_messages(request.messages),
        }

        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.stop_sequences:
            payload["stop"] = request.stop_sequences
        if request.metadata:
            payload["metadata"] = request.metadata

        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in request.tools
            ]

        tool_choice = self._translate_tool_choice(request)
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}

        return payload

    def _translate_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        translated: list[dict[str, Any]] = []

        for message in messages:
            role = message.role.value
            if role == "tool":
                translated.append(self._translate_tool_result_message(message))
                continue

            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []

            for part in message.content:
                if part.kind == ContentKind.TEXT and part.text is not None:
                    text_parts.append(part.text)
                elif part.kind == ContentKind.TOOL_CALL and part.tool_call is not None:
                    tool_calls.append(self._translate_tool_call(part.tool_call))

            content = "".join(text_parts)
            translated_message: dict[str, Any] = {
                "role": role,
                "content": None if role == "assistant" and not content and tool_calls else content,
            }

            if tool_calls:
                translated_message["tool_calls"] = tool_calls

            translated.append(translated_message)

        return translated

    def _translate_tool_result_message(self, message: Message) -> dict[str, Any]:
        tool_call_id = message.tool_call_id or ""
        content: str | dict[str, Any] | list = ""

        for part in message.content:
            if part.kind == ContentKind.TOOL_RESULT and part.tool_result is not None:
                tool_call_id = part.tool_result.tool_call_id
                content = part.tool_result.content
                break
            if part.kind == ContentKind.TEXT and part.text is not None and content == "":
                content = part.text

        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": self._stringify_content(content),
        }

    def _stringify_content(self, content: str | dict[str, Any] | list) -> str:
        if isinstance(content, str):
            return content
        return json.dumps(content)

    def _translate_tool_call(self, tool_call: ToolCallData) -> dict[str, Any]:
        arguments: str
        if isinstance(tool_call.arguments, dict):
            arguments = json.dumps(tool_call.arguments)
        else:
            arguments = tool_call.arguments

        return {
            "id": tool_call.id,
            "type": "function",
            "function": {
                "name": tool_call.name,
                "arguments": arguments,
            },
        }

    def _translate_tool_choice(self, request: Request) -> str | dict[str, Any] | None:
        if request.tool_choice is None:
            return None

        mode = request.tool_choice.mode
        if mode in ("auto", "none", "required"):
            return mode
        if mode == "named" and request.tool_choice.tool_name:
            return {
                "type": "function",
                "function": {"name": request.tool_choice.tool_name},
            }
        return None

    async def complete(self, request: Request) -> Response:
        response = await self._client.post(
            f"{self._base_url}/v1/chat/completions",
            json=self._build_payload(request),
            headers=self._build_headers(),
        )

        if response.status_code >= 400:
            raise self._error_from_response(response)

        raw = response.json()
        return self._parse_response(raw)

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        text_id = "0"
        text_started = False
        text_ended = False
        tool_states: dict[int, dict[str, Any]] = {}
        latest_finish_reason: str | None = None
        latest_usage: dict[str, Any] | None = None
        finish_emitted = False

        async with self._client.stream(
            "POST",
            f"{self._base_url}/v1/chat/completions",
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

                usage = event.get("usage")
                if isinstance(usage, dict):
                    latest_usage = usage

                choices = event.get("choices")
                if not isinstance(choices, list) or not choices:
                    continue

                choice = choices[0]
                if not isinstance(choice, dict):
                    continue

                delta = choice.get("delta")
                if not isinstance(delta, dict):
                    delta = {}

                content_delta = delta.get("content")
                if isinstance(content_delta, str) and content_delta:
                    if not text_started:
                        text_started = True
                        yield StreamEvent(type=StreamEventType.TEXT_START, text_id=text_id)
                    yield StreamEvent(
                        type=StreamEventType.TEXT_DELTA,
                        delta=content_delta,
                        text_id=text_id,
                    )

                tool_calls = delta.get("tool_calls")
                if isinstance(tool_calls, list):
                    for tool_call in tool_calls:
                        if not isinstance(tool_call, dict):
                            continue

                        index = self._to_index(tool_call.get("index"))
                        state = tool_states.setdefault(
                            index,
                            {
                                "id": "",
                                "name": "",
                                "raw_arguments": "",
                                "started": False,
                                "ended": False,
                            },
                        )

                        call_id = tool_call.get("id")
                        if isinstance(call_id, str) and call_id:
                            state["id"] = call_id

                        function = tool_call.get("function")
                        if isinstance(function, dict):
                            name = function.get("name")
                            if isinstance(name, str) and name:
                                state["name"] = name

                        if not state["started"]:
                            state["started"] = True
                            yield StreamEvent(
                                type=StreamEventType.TOOL_CALL_START,
                                tool_call=ToolCall(
                                    id=state["id"],
                                    name=state["name"],
                                    arguments={},
                                ),
                            )

                        if isinstance(function, dict):
                            arguments_delta = function.get("arguments")
                            if isinstance(arguments_delta, str) and arguments_delta:
                                state["raw_arguments"] += arguments_delta
                                yield StreamEvent(
                                    type=StreamEventType.TOOL_CALL_DELTA,
                                    tool_call=ToolCall(
                                        id=state["id"],
                                        name=state["name"],
                                        arguments={},
                                        raw_arguments=arguments_delta,
                                    ),
                                )

                finish_reason = choice.get("finish_reason")
                if isinstance(finish_reason, str):
                    latest_finish_reason = finish_reason

                    if text_started and not text_ended:
                        text_ended = True
                        yield StreamEvent(type=StreamEventType.TEXT_END, text_id=text_id)

                    for index in sorted(tool_states):
                        state = tool_states[index]
                        if state["started"] and not state["ended"]:
                            state["ended"] = True
                            raw_arguments = state["raw_arguments"]
                            yield StreamEvent(
                                type=StreamEventType.TOOL_CALL_END,
                                tool_call=ToolCall(
                                    id=state["id"],
                                    name=state["name"],
                                    arguments=self._parse_arguments(raw_arguments),
                                    raw_arguments=raw_arguments if raw_arguments else None,
                                ),
                            )

                    finish_emitted = True
                    yield StreamEvent(
                        type=StreamEventType.FINISH,
                        finish_reason=self._map_finish_reason(latest_finish_reason),
                        usage=self._parse_usage(latest_usage),
                    )

        if not finish_emitted:
            if text_started and not text_ended:
                yield StreamEvent(type=StreamEventType.TEXT_END, text_id=text_id)

            for index in sorted(tool_states):
                state = tool_states[index]
                if state["started"] and not state["ended"]:
                    raw_arguments = state["raw_arguments"]
                    yield StreamEvent(
                        type=StreamEventType.TOOL_CALL_END,
                        tool_call=ToolCall(
                            id=state["id"],
                            name=state["name"],
                            arguments=self._parse_arguments(raw_arguments),
                            raw_arguments=raw_arguments if raw_arguments else None,
                        ),
                    )

            yield StreamEvent(
                type=StreamEventType.FINISH,
                finish_reason=self._map_finish_reason(latest_finish_reason),
                usage=self._parse_usage(latest_usage),
            )

    def _to_index(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

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

        message = "OpenAI-compatible API error"
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
        choices = raw.get("choices")
        first_choice = choices[0] if isinstance(choices, list) and choices else {}
        choice = first_choice if isinstance(first_choice, dict) else {}
        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}

        content_parts: list[ContentPart] = []
        has_tool_calls = False

        content = message.get("content")
        if isinstance(content, str) and content:
            content_parts.append(ContentPart.text(content))
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    content_parts.append(ContentPart.text(block["text"]))

        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                function = (
                    tool_call.get("function")
                    if isinstance(tool_call.get("function"), dict)
                    else {}
                )
                has_tool_calls = True
                content_parts.append(
                    ContentPart.tool_call(
                        ToolCallData(
                            id=str(tool_call.get("id") or ""),
                            name=str(function.get("name") or ""),
                            arguments=self._parse_arguments(function.get("arguments")),
                        )
                    )
                )

        finish_reason_raw = choice.get("finish_reason")

        return Response(
            id=str(raw.get("id") or ""),
            model=str(raw.get("model") or ""),
            provider=self.name,
            message=Message(role=Role.ASSISTANT, content=content_parts),
            finish_reason=self._map_finish_reason(
                finish_reason_raw if isinstance(finish_reason_raw, str) else None,
                has_tool_calls=has_tool_calls,
            ),
            usage=self._parse_usage(raw.get("usage")),
            raw=raw,
        )

    def _parse_usage(self, usage: Any) -> Usage:
        usage_data = usage if isinstance(usage, dict) else {}
        completion_details = (
            usage_data.get("completion_tokens_details")
            if isinstance(usage_data.get("completion_tokens_details"), dict)
            else {}
        )

        return Usage(
            input_tokens=int(usage_data.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage_data.get("completion_tokens", 0) or 0),
            reasoning_tokens=int(completion_details["reasoning_tokens"])
            if completion_details.get("reasoning_tokens") is not None
            else None,
            raw=usage_data,
        )

    def _map_finish_reason(
        self,
        raw_reason: str | None,
        *,
        has_tool_calls: bool = False,
    ) -> FinishReason:
        if has_tool_calls or raw_reason in ("tool_calls", "function_call"):
            return FinishReason(reason="tool_calls", raw=raw_reason)

        mapping = {
            "stop": "stop",
            "length": "length",
            "content_filter": "content_filter",
            "error": "error",
        }
        return FinishReason(reason=mapping.get(raw_reason, "other"), raw=raw_reason)

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
