"""High-level helpers for common LLM workflows."""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from typing import Any, Protocol

from attractor_llm.client import Client
from attractor_llm.errors import NoObjectGeneratedError
from attractor_llm.request import Request, ResponseFormat, ToolChoice, ToolDefinition
from attractor_llm.response import FinishReason, Response, StreamEvent, StreamEventType, Usage
from attractor_llm.types import (
    ContentPart,
    Message,
    Role,
    ThinkingData,
    ToolCallData,
    ToolResultData,
)


class ToolHandler(Protocol):
    def __call__(self, arguments: dict[str, Any]) -> Any: ...


@dataclass
class GenerateResult:
    steps: list[Response]
    total_usage: Usage

    @property
    def response(self) -> Response:
        return self.steps[-1]


class StreamAccumulator:
    """Accumulate stream events into a final Response."""

    def __init__(self, *, model: str, provider: str):
        self._model = model
        self._provider = provider
        self._text_parts: list[str] = []
        self._reasoning_parts: list[str] = []
        self._tool_calls: list[dict[str, Any]] = []
        self._tool_index: dict[str, int] = {}
        self._finish_reason: FinishReason | None = None
        self._usage: Usage | None = None
        self._response: Response | None = None

    def process(self, event: StreamEvent) -> None:
        if event.response is not None:
            self._response = event.response

        if event.type == StreamEventType.TEXT_DELTA and event.delta:
            self._text_parts.append(event.delta)
        elif event.type == StreamEventType.REASONING_DELTA and event.reasoning_delta:
            self._reasoning_parts.append(event.reasoning_delta)
        elif event.type == StreamEventType.TOOL_CALL_START and event.tool_call is not None:
            self._ensure_tool_call(event.tool_call.id, event.tool_call.name)
        elif event.type == StreamEventType.TOOL_CALL_DELTA and event.tool_call is not None:
            self._merge_tool_call(
                event.tool_call.id, event.tool_call.name, event.tool_call.raw_arguments
            )
        elif event.type == StreamEventType.TOOL_CALL_END and event.tool_call is not None:
            self._merge_tool_call_end(
                event.tool_call.id, event.tool_call.name, event.tool_call.arguments
            )
        elif event.type == StreamEventType.FINISH:
            if event.finish_reason is not None:
                self._finish_reason = event.finish_reason
            if event.usage is not None:
                self._usage = event.usage

    def response(self) -> Response:
        if self._response is not None:
            return self._response

        if self._finish_reason is None or self._usage is None:
            raise RuntimeError("Stream has not completed yet")

        content: list[ContentPart] = []
        text = "".join(self._text_parts)
        if text:
            content.append(ContentPart.text(text))

        reasoning = "".join(self._reasoning_parts)
        if reasoning:
            content.append(ContentPart.thinking(ThinkingData(text=reasoning)))

        for tool_call in self._tool_calls:
            arguments = self._parse_tool_arguments(tool_call)
            content.append(
                ContentPart.tool_call(
                    ToolCallData(
                        id=tool_call["id"],
                        name=tool_call["name"],
                        arguments=arguments,
                    )
                )
            )

        return Response(
            id="",
            model=self._model,
            provider=self._provider,
            message=Message(role=Role.ASSISTANT, content=content),
            finish_reason=self._finish_reason,
            usage=self._usage,
        )

    def _ensure_tool_call(self, tool_call_id: str, tool_name: str) -> dict[str, Any]:
        if tool_call_id in self._tool_index:
            return self._tool_calls[self._tool_index[tool_call_id]]

        state = {"id": tool_call_id, "name": tool_name, "raw_arguments": "", "arguments": {}}
        self._tool_index[tool_call_id] = len(self._tool_calls)
        self._tool_calls.append(state)
        return state

    def _merge_tool_call(self, tool_call_id: str, tool_name: str, raw_delta: str | None) -> None:
        state = self._ensure_tool_call(tool_call_id, tool_name)
        if raw_delta:
            state["raw_arguments"] += raw_delta

    def _merge_tool_call_end(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        state = self._ensure_tool_call(tool_call_id, tool_name)
        if arguments:
            state["arguments"] = arguments

    def _parse_tool_arguments(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        arguments = tool_call.get("arguments")
        if isinstance(arguments, dict) and arguments:
            return arguments

        raw_arguments = tool_call.get("raw_arguments")
        if not isinstance(raw_arguments, str) or not raw_arguments:
            return {}

        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}


class StreamResult:
    """Async iterator wrapper with final response access."""

    def __init__(self, *, events: Any, accumulator: StreamAccumulator):
        self._events = events.__aiter__()
        self._accumulator = accumulator
        self._done = False

    def __aiter__(self) -> StreamResult:
        return self

    async def __anext__(self) -> StreamEvent:
        if self._done:
            raise StopAsyncIteration

        try:
            event = await anext(self._events)
        except StopAsyncIteration:
            self._done = True
            raise

        self._accumulator.process(event)
        return event

    async def response(self) -> Response:
        if not self._done:
            async for _ in self:
                pass
        return self._accumulator.response()


async def generate(
    *,
    client: Client,
    model: str,
    prompt: str | None = None,
    messages: list[Message] | None = None,
    system: str | None = None,
    provider: str | None = None,
    tools: list[ToolDefinition] | None = None,
    tool_handlers: dict[str, ToolHandler] | None = None,
    tool_choice: ToolChoice | None = None,
    response_format: ResponseFormat | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    stop_sequences: list[str] | None = None,
    reasoning_effort: str | None = None,
    metadata: dict[str, str] | None = None,
    provider_options: dict[str, Any] | None = None,
    max_steps: int = 8,
) -> GenerateResult:
    request_messages = _build_messages(prompt=prompt, messages=messages, system=system)
    handlers = tool_handlers or {}

    steps: list[Response] = []
    total_usage = Usage(input_tokens=0, output_tokens=0)

    for _ in range(max_steps):
        request = Request(
            model=model,
            messages=list(request_messages),
            provider=provider,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stop_sequences=stop_sequences,
            reasoning_effort=reasoning_effort,
            metadata=metadata,
            provider_options=provider_options,
        )
        response = await client.complete(request)
        steps.append(response)
        total_usage = total_usage + response.usage

        if not tools or not response.tool_calls:
            break

        request_messages.append(response.message)
        for tool_call in response.tool_calls:
            handler = handlers.get(tool_call.name)
            if handler is None:
                tool_result = Message(
                    role=Role.TOOL,
                    content=[
                        ContentPart.tool_result(
                            _tool_result_data(
                                tool_call_id=tool_call.id,
                                content=f"Unknown tool: {tool_call.name}",
                                is_error=True,
                            )
                        )
                    ],
                    tool_call_id=tool_call.id,
                )
                request_messages.append(tool_result)
                continue

            try:
                result = handler(tool_call.arguments)
                if inspect.isawaitable(result):
                    result = await result
                is_error = False
            except Exception as error:
                result = str(error)
                is_error = True

            tool_result = Message(
                role=Role.TOOL,
                content=[
                    ContentPart.tool_result(
                        _tool_result_data(
                            tool_call_id=tool_call.id,
                            content=result,
                            is_error=is_error,
                        )
                    )
                ],
                tool_call_id=tool_call.id,
            )
            request_messages.append(tool_result)

    return GenerateResult(steps=steps, total_usage=total_usage)


async def stream(
    *,
    client: Client,
    model: str,
    prompt: str | None = None,
    messages: list[Message] | None = None,
    system: str | None = None,
    provider: str | None = None,
    tools: list[ToolDefinition] | None = None,
    tool_choice: ToolChoice | None = None,
    response_format: ResponseFormat | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    stop_sequences: list[str] | None = None,
    reasoning_effort: str | None = None,
    metadata: dict[str, str] | None = None,
    provider_options: dict[str, Any] | None = None,
) -> StreamResult:
    request = Request(
        model=model,
        messages=_build_messages(prompt=prompt, messages=messages, system=system),
        provider=provider,
        tools=tools,
        tool_choice=tool_choice,
        response_format=response_format,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        stop_sequences=stop_sequences,
        reasoning_effort=reasoning_effort,
        metadata=metadata,
        provider_options=provider_options,
    )
    return StreamResult(
        events=client.stream(request),
        accumulator=StreamAccumulator(model=model, provider=provider or ""),
    )


async def generate_object(
    *,
    client: Client,
    model: str,
    json_schema: dict[str, Any],
    prompt: str | None = None,
    messages: list[Message] | None = None,
    system: str | None = None,
    provider: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    stop_sequences: list[str] | None = None,
    reasoning_effort: str | None = None,
    metadata: dict[str, str] | None = None,
    provider_options: dict[str, Any] | None = None,
) -> Any:
    effective_provider = provider or _default_provider_name(client)
    use_json_schema = effective_provider in {"openai", "gemini"}

    if use_json_schema:
        result = await generate(
            client=client,
            model=model,
            prompt=prompt,
            messages=messages,
            system=system,
            provider=provider,
            response_format=ResponseFormat(
                type="json_schema",
                json_schema=json_schema,
                strict=True,
            ),
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stop_sequences=stop_sequences,
            reasoning_effort=reasoning_effort,
            metadata=metadata,
            provider_options=provider_options,
        )
    else:
        schema_text = json.dumps(json_schema, sort_keys=True)
        fallback_instruction = (
            f"Respond with valid JSON only that matches this JSON schema: {schema_text}"
        )
        if prompt is not None:
            fallback_prompt = f"{prompt}\n\n{fallback_instruction}"
            fallback_messages = None
        else:
            fallback_prompt = None
            base_messages = list(messages or [])
            base_messages.append(Message.user(fallback_instruction))
            fallback_messages = base_messages

        result = await generate(
            client=client,
            model=model,
            prompt=fallback_prompt,
            messages=fallback_messages,
            system=system,
            provider=provider,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stop_sequences=stop_sequences,
            reasoning_effort=reasoning_effort,
            metadata=metadata,
            provider_options=provider_options,
        )

    output = result.response.text.strip()
    try:
        return json.loads(output)
    except json.JSONDecodeError as error:
        raise NoObjectGeneratedError("Failed to parse generated object") from error


def _build_messages(
    *,
    prompt: str | None,
    messages: list[Message] | None,
    system: str | None,
) -> list[Message]:
    if (prompt is None and messages is None) or (prompt is not None and messages is not None):
        raise ValueError("Pass either prompt or messages")

    request_messages = list(messages) if messages is not None else [Message.user(prompt or "")]

    if system is not None:
        request_messages = [Message.system(system), *request_messages]

    return request_messages


def _default_provider_name(client: Client) -> str | None:
    return getattr(client, "_default_provider", None)


def _tool_result_data(*, tool_call_id: str, content: Any, is_error: bool) -> ToolResultData:
    normalized = content if isinstance(content, (dict, str)) else str(content)
    return ToolResultData(
        tool_call_id=tool_call_id,
        content=normalized,
        is_error=is_error,
    )
