"""Gemini provider adapter."""

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


class GeminiAdapter(ProviderAdapter):
    """Adapter for Gemini's generateContent API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com",
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 60.0,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

    @property
    def name(self) -> str:
        return "gemini"

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _build_headers(self) -> dict[str, str]:
        return {"content-type": "application/json"}

    def _build_payload(self, request: Request) -> dict[str, Any]:
        payload: dict[str, Any] = {"contents": self._translate_messages(request.messages)}

        system_instruction = self._extract_system_instruction(request.messages)
        if system_instruction is not None:
            payload["systemInstruction"] = system_instruction

        if request.tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.parameters,
                        }
                        for tool in request.tools
                    ]
                }
            ]

        tool_config = self._translate_tool_choice(request)
        if tool_config is not None:
            payload["toolConfig"] = tool_config

        generation_config = self._translate_generation_config(request)
        if generation_config:
            payload["generationConfig"] = generation_config

        return payload

    def _extract_system_instruction(self, messages: list[Message]) -> dict[str, Any] | None:
        parts: list[dict[str, str]] = []

        for message in messages:
            if message.role not in (Role.SYSTEM, Role.DEVELOPER):
                continue
            for part in message.content:
                if part.kind == ContentKind.TEXT and part.text is not None:
                    parts.append({"text": part.text})

        if not parts:
            return None
        return {"parts": parts}

    def _translate_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        translated: list[dict[str, Any]] = []
        call_name_by_id: dict[str, str] = {}
        anonymous_call_names: list[str] = []
        synthetic_counter = 0

        for message in messages:
            if message.role in (Role.SYSTEM, Role.DEVELOPER):
                continue

            role = "model" if message.role == Role.ASSISTANT else "user"
            parts: list[dict[str, Any]] = []

            for part in message.content:
                if part.kind == ContentKind.TEXT and part.text is not None:
                    parts.append({"text": part.text})

                elif part.kind == ContentKind.TOOL_CALL and part.tool_call is not None:
                    tool_call = part.tool_call
                    call_id = tool_call.id.strip()
                    if not call_id:
                        synthetic_counter += 1
                        call_id = f"call_{synthetic_counter}"
                        anonymous_call_names.append(tool_call.name)

                    call_name_by_id[call_id] = tool_call.name
                    args = self._parse_arguments(tool_call.arguments)
                    parts.append(
                        {
                            "functionCall": {
                                "id": call_id,
                                "name": tool_call.name,
                                "args": args,
                            }
                        }
                    )

                elif part.kind == ContentKind.TOOL_RESULT and part.tool_result is not None:
                    result = part.tool_result
                    tool_call_id = result.tool_call_id.strip()
                    function_name = call_name_by_id.get(tool_call_id)
                    if function_name is None and not tool_call_id and anonymous_call_names:
                        function_name = anonymous_call_names.pop(0)
                    if function_name is None:
                        function_name = "tool"

                    response_payload: dict[str, Any]
                    if isinstance(result.content, dict):
                        response_payload = dict(result.content)
                    else:
                        response_payload = {"content": result.content}
                    if result.is_error:
                        response_payload["is_error"] = True

                    parts.append(
                        {
                            "functionResponse": {
                                "name": function_name,
                                "response": response_payload,
                            }
                        }
                    )

            if parts:
                translated.append({"role": role, "parts": parts})

        return translated

    def _parse_arguments(self, arguments: dict[str, Any] | str) -> dict[str, Any]:
        if isinstance(arguments, dict):
            return arguments
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _translate_tool_choice(self, request: Request) -> dict[str, Any] | None:
        if request.tool_choice is None:
            return None

        mode = request.tool_choice.mode
        if mode == "none":
            return {"functionCallingConfig": {"mode": "NONE"}}
        if mode == "required":
            return {"functionCallingConfig": {"mode": "ANY"}}
        if mode == "named" and request.tool_choice.tool_name:
            return {
                "functionCallingConfig": {
                    "mode": "ANY",
                    "allowedFunctionNames": [request.tool_choice.tool_name],
                }
            }
        if mode == "auto":
            return {"functionCallingConfig": {"mode": "AUTO"}}
        return None

    def _translate_generation_config(self, request: Request) -> dict[str, Any]:
        config: dict[str, Any] = {}

        if request.temperature is not None:
            config["temperature"] = request.temperature
        if request.top_p is not None:
            config["topP"] = request.top_p
        if request.max_tokens is not None:
            config["maxOutputTokens"] = request.max_tokens
        if request.stop_sequences:
            config["stopSequences"] = request.stop_sequences

        if (
            request.response_format
            and request.response_format.type == "json_schema"
            and request.response_format.json_schema is not None
        ):
            config["responseMimeType"] = "application/json"
            config["responseSchema"] = request.response_format.json_schema

        return config

    async def complete(self, request: Request) -> Response:
        response = await self._client.post(
            f"{self._base_url}/v1beta/models/{request.model}:generateContent?key={self._api_key}",
            json=self._build_payload(request),
            headers=self._build_headers(),
        )

        if response.status_code >= 400:
            raise self._error_from_response(response)

        raw = response.json()
        return self._parse_response(raw, request.model)

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        text_id = "0"
        text_started = False
        saw_tool_call = False
        finish_emitted = False
        latest_finish_reason: str | None = None
        latest_usage: dict[str, Any] | None = None

        async with self._client.stream(
            "POST",
            f"{self._base_url}/v1beta/models/{request.model}:streamGenerateContent?alt=sse&key={self._api_key}",
            json=self._build_payload(request),
            headers=self._build_headers(),
        ) as response:
            if response.status_code >= 400:
                raise self._error_from_response(response)

            async for _, data in parse_sse_events(response.aiter_lines()):
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue

                candidates = event.get("candidates")
                if not isinstance(candidates, list) or not candidates:
                    continue

                candidate = candidates[0]
                if not isinstance(candidate, dict):
                    continue

                content = candidate.get("content")
                parts = content.get("parts") if isinstance(content, dict) else None
                if isinstance(parts, list):
                    for part in parts:
                        if not isinstance(part, dict):
                            continue

                        text = part.get("text")
                        if isinstance(text, str) and text:
                            if not text_started:
                                text_started = True
                                yield StreamEvent(type=StreamEventType.TEXT_START, text_id=text_id)
                            yield StreamEvent(
                                type=StreamEventType.TEXT_DELTA,
                                delta=text,
                                text_id=text_id,
                            )

                        function_call = part.get("functionCall")
                        if isinstance(function_call, dict):
                            saw_tool_call = True
                            tool_call = ToolCall(
                                id=str(
                                    function_call.get("id") or function_call.get("name") or "call"
                                ),
                                name=str(function_call.get("name") or ""),
                                arguments=function_call.get("args")
                                if isinstance(function_call.get("args"), dict)
                                else {},
                            )
                            yield StreamEvent(
                                type=StreamEventType.TOOL_CALL_START, tool_call=tool_call
                            )
                            yield StreamEvent(
                                type=StreamEventType.TOOL_CALL_END, tool_call=tool_call
                            )

                finish_reason = candidate.get("finishReason")
                if isinstance(finish_reason, str):
                    latest_finish_reason = finish_reason

                usage_metadata = event.get("usageMetadata")
                if isinstance(usage_metadata, dict):
                    latest_usage = usage_metadata

                if latest_finish_reason is not None and not finish_emitted:
                    finish_emitted = True
                    yield StreamEvent(
                        type=StreamEventType.FINISH,
                        finish_reason=self._map_finish_reason(
                            latest_finish_reason,
                            has_tool_call=saw_tool_call,
                        ),
                        usage=self._parse_usage(latest_usage),
                    )

        if not finish_emitted:
            yield StreamEvent(
                type=StreamEventType.FINISH,
                finish_reason=self._map_finish_reason(
                    latest_finish_reason,
                    has_tool_call=saw_tool_call,
                ),
                usage=self._parse_usage(latest_usage),
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

        message = "Gemini API error"
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

    def _parse_response(self, raw: dict[str, Any], model: str) -> Response:
        content_parts: list[ContentPart] = []
        saw_tool_call = False

        candidates = raw.get("candidates")
        first_candidate = candidates[0] if isinstance(candidates, list) and candidates else {}
        candidate = first_candidate if isinstance(first_candidate, dict) else {}
        content = candidate.get("content")
        parts = content.get("parts") if isinstance(content, dict) else []

        if isinstance(parts, list):
            for part in parts:
                if not isinstance(part, dict):
                    continue

                text = part.get("text")
                if isinstance(text, str):
                    content_parts.append(ContentPart.text(text))

                function_call = part.get("functionCall")
                if isinstance(function_call, dict):
                    saw_tool_call = True
                    content_parts.append(
                        ContentPart.tool_call(
                            ToolCallData(
                                id=str(
                                    function_call.get("id") or function_call.get("name") or "call"
                                ),
                                name=str(function_call.get("name") or ""),
                                arguments=function_call.get("args")
                                if isinstance(function_call.get("args"), dict)
                                else {},
                            )
                        )
                    )

        return Response(
            id=str(raw.get("responseId") or ""),
            model=str(raw.get("modelVersion") or model),
            provider=self.name,
            message=Message(role=Role.ASSISTANT, content=content_parts),
            finish_reason=self._map_finish_reason(
                candidate.get("finishReason")
                if isinstance(candidate.get("finishReason"), str)
                else None,
                has_tool_call=saw_tool_call,
            ),
            usage=self._parse_usage(raw.get("usageMetadata")),
            raw=raw,
        )

    def _parse_usage(self, usage_metadata: Any) -> Usage:
        usage_data = usage_metadata if isinstance(usage_metadata, dict) else {}
        input_tokens = int(usage_data.get("promptTokenCount", 0) or 0)
        output_tokens = int(usage_data.get("candidatesTokenCount", 0) or 0)

        if output_tokens == 0 and usage_data.get("totalTokenCount") is not None:
            output_tokens = max(int(usage_data.get("totalTokenCount", 0) or 0) - input_tokens, 0)

        return Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=int(usage_data["thoughtsTokenCount"])
            if usage_data.get("thoughtsTokenCount") is not None
            else None,
            cache_read_tokens=int(usage_data["cachedContentTokenCount"])
            if usage_data.get("cachedContentTokenCount") is not None
            else None,
            raw=usage_data,
        )

    def _map_finish_reason(self, raw_reason: str | None, *, has_tool_call: bool) -> FinishReason:
        if has_tool_call:
            return FinishReason(reason="tool_calls", raw=raw_reason)

        mapping = {
            "STOP": "stop",
            "MAX_TOKENS": "length",
            "SAFETY": "content_filter",
            "PROHIBITED_CONTENT": "content_filter",
            "MALFORMED_FUNCTION_CALL": "error",
        }
        return FinishReason(reason=mapping.get(raw_reason, "other"), raw=raw_reason)
