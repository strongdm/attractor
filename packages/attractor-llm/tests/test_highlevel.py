"""Tests for high-level generation helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from attractor_llm.errors import NoObjectGeneratedError
from attractor_llm.highlevel import StreamAccumulator, generate, generate_object, stream
from attractor_llm.request import Request, ResponseFormat, ToolDefinition
from attractor_llm.response import (
    FinishReason,
    Response,
    StreamEvent,
    StreamEventType,
    ToolCall,
    Usage,
)
from attractor_llm.types import ContentPart, Message, Role, ToolCallData


class FakeClient:
    def __init__(
        self,
        responses: list[Response] | None = None,
        stream_events: list[StreamEvent] | None = None,
    ):
        self.requests: list[Request] = []
        self._responses = list(responses or [])
        self._stream_events = list(stream_events or [])

    async def complete(self, request: Request) -> Response:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("No fake response configured")
        return self._responses.pop(0)

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        self.requests.append(request)
        for event in self._stream_events:
            yield event


def _response(
    *,
    provider: str = "openai",
    text: str = "ok",
    usage: Usage | None = None,
    content: list[Any] | None = None,
) -> Response:
    return Response(
        id="resp_1",
        model="test-model",
        provider=provider,
        message=Message(
            role=Role.ASSISTANT,
            content=content if content is not None else [ContentPart.text(text)],
        ),
        finish_reason=FinishReason(reason="stop"),
        usage=usage or Usage(input_tokens=1, output_tokens=2),
    )


class TestGenerate:
    async def test_requires_prompt_or_messages(self):
        client = FakeClient(responses=[_response()])

        with pytest.raises(ValueError, match="either prompt or messages"):
            await generate(client=client, model="m")

    async def test_rejects_prompt_and_messages_together(self):
        client = FakeClient(responses=[_response()])

        with pytest.raises(ValueError, match="either prompt or messages"):
            await generate(
                client=client,
                model="m",
                prompt="hello",
                messages=[Message.user("world")],
            )

    async def test_builds_request_and_prepends_system_message(self):
        client = FakeClient(responses=[_response(text="done")])

        result = await generate(
            client=client,
            model="m",
            prompt="Hello",
            system="Be concise",
        )

        assert result.response.text == "done"
        request = client.requests[0]
        assert request.messages[0].role == Role.SYSTEM
        assert request.messages[0].text == "Be concise"
        assert request.messages[1].role == Role.USER
        assert request.messages[1].text == "Hello"

    async def test_executes_tools_in_order_and_handles_unknown_tools(self):
        first = _response(
            provider="openai",
            content=[
                ContentPart.tool_call(
                    ToolCallData(id="call_known", name="known_tool", arguments={"n": 1})
                ),
                ContentPart.tool_call(
                    ToolCallData(id="call_unknown", name="unknown_tool", arguments={"n": 2})
                ),
            ],
            usage=Usage(input_tokens=10, output_tokens=5),
        )
        second = _response(
            provider="openai", text="final", usage=Usage(input_tokens=3, output_tokens=4)
        )
        client = FakeClient(responses=[first, second])

        calls: list[dict[str, Any]] = []

        async def known_handler(arguments: dict[str, Any]) -> dict[str, Any]:
            calls.append(arguments)
            return {"ok": True}

        result = await generate(
            client=client,
            model="m",
            prompt="run tools",
            tools=[
                ToolDefinition(
                    name="known_tool",
                    description="Known",
                    parameters={"type": "object", "properties": {"n": {"type": "integer"}}},
                )
            ],
            tool_handlers={"known_tool": known_handler},
        )

        assert calls == [{"n": 1}]
        assert len(result.steps) == 2
        assert result.response.text == "final"
        assert result.total_usage == Usage(input_tokens=13, output_tokens=9)

        second_request = client.requests[1]
        tool_messages = [m for m in second_request.messages if m.role == Role.TOOL]
        assert len(tool_messages) == 2
        first_result = tool_messages[0].content[0].tool_result
        second_result = tool_messages[1].content[0].tool_result
        assert first_result is not None and first_result.tool_call_id == "call_known"
        assert first_result.content == {"ok": True}
        assert first_result.is_error is False
        assert second_result is not None and second_result.tool_call_id == "call_unknown"
        assert second_result.is_error is True


class TestStream:
    async def test_stream_wrapper_accumulates_response(self):
        events = [
            StreamEvent(type=StreamEventType.TEXT_START, text_id="0"),
            StreamEvent(type=StreamEventType.TEXT_DELTA, text_id="0", delta="Hello"),
            StreamEvent(type=StreamEventType.REASONING_START),
            StreamEvent(type=StreamEventType.REASONING_DELTA, reasoning_delta="Think"),
            StreamEvent(
                type=StreamEventType.TOOL_CALL_START,
                tool_call=ToolCall(id="call_1", name="lookup", arguments={}),
            ),
            StreamEvent(
                type=StreamEventType.TOOL_CALL_END,
                tool_call=ToolCall(id="call_1", name="lookup", arguments={"q": "x"}),
            ),
            StreamEvent(
                type=StreamEventType.FINISH,
                finish_reason=FinishReason(reason="stop"),
                usage=Usage(input_tokens=4, output_tokens=2),
            ),
        ]
        client = FakeClient(stream_events=events)

        result = await stream(client=client, model="m", prompt="hello")
        consumed = []
        async for event in result:
            consumed.append(event.type)

        assert consumed[-1] == StreamEventType.FINISH
        response = await result.response()
        assert response.text == "Hello"
        assert response.reasoning == "Think"
        assert response.tool_calls[0].name == "lookup"
        assert response.usage == Usage(input_tokens=4, output_tokens=2)

    async def test_stream_response_consumes_when_not_iterated(self):
        client = FakeClient(
            stream_events=[
                StreamEvent(type=StreamEventType.TEXT_DELTA, text_id="0", delta="A"),
                StreamEvent(
                    type=StreamEventType.FINISH,
                    finish_reason=FinishReason(reason="stop"),
                    usage=Usage(input_tokens=1, output_tokens=1),
                ),
            ]
        )

        result = await stream(client=client, model="m", prompt="hi")
        response = await result.response()
        assert response.text == "A"


class TestStreamAccumulator:
    def test_accumulates_text_reasoning_and_tool_call(self):
        accumulator = StreamAccumulator(model="m", provider="openai")

        accumulator.process(StreamEvent(type=StreamEventType.TEXT_DELTA, delta="Hello"))
        accumulator.process(
            StreamEvent(type=StreamEventType.REASONING_DELTA, reasoning_delta="Think")
        )
        accumulator.process(
            StreamEvent(
                type=StreamEventType.TOOL_CALL_START,
                tool_call=ToolCall(id="call_1", name="search", arguments={}),
            )
        )
        accumulator.process(
            StreamEvent(
                type=StreamEventType.TOOL_CALL_DELTA,
                tool_call=ToolCall(
                    id="call_1",
                    name="search",
                    arguments={},
                    raw_arguments='{"q": "hi"}',
                ),
            )
        )
        accumulator.process(
            StreamEvent(
                type=StreamEventType.FINISH,
                finish_reason=FinishReason(reason="stop"),
                usage=Usage(input_tokens=1, output_tokens=1),
            )
        )

        response = accumulator.response()
        assert response.text == "Hello"
        assert response.reasoning == "Think"
        assert response.tool_calls[0].arguments == {"q": "hi"}


class TestGenerateObject:
    async def test_uses_json_schema_for_openai_and_parses_json(self):
        client = FakeClient(responses=[_response(provider="openai", text='{"name":"Ada"}')])
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }

        obj = await generate_object(
            client=client,
            model="m",
            prompt="Who?",
            provider="openai",
            json_schema=schema,
        )

        request = client.requests[0]
        assert request.response_format == ResponseFormat(
            type="json_schema",
            json_schema=schema,
            strict=True,
        )
        assert obj == {"name": "Ada"}

    async def test_fallback_prompt_for_non_schema_provider(self):
        client = FakeClient(responses=[_response(provider="anthropic", text='{"ok":true}')])

        schema = {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
        }
        obj = await generate_object(
            client=client,
            model="m",
            prompt="Return status",
            provider="anthropic",
            json_schema=schema,
        )

        request = client.requests[0]
        assert request.response_format is None
        assert "JSON" in request.messages[0].text
        assert obj == {"ok": True}

    async def test_raises_when_output_is_not_json(self):
        client = FakeClient(responses=[_response(provider="openai", text="not-json")])

        with pytest.raises(NoObjectGeneratedError):
            await generate_object(
                client=client,
                model="m",
                prompt="Return data",
                provider="openai",
                json_schema={"type": "object"},
            )
