"""Tests for Anthropic HTTP and streaming behavior."""

import json

import httpx
import pytest

from attractor_llm.adapters.anthropic import AnthropicAdapter
from attractor_llm.errors import RateLimitError
from attractor_llm.request import Request
from attractor_llm.response import StreamEventType
from attractor_llm.types import ContentKind, Message


@pytest.mark.asyncio
async def test_complete_maps_response_and_applies_beta_headers():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["headers"] = dict(request.headers)
        captured["json"] = json.loads(request.content.decode("utf-8"))
        response_body = {
            "id": "msg_1",
            "model": "claude-sonnet-4-5-20250929",
            "stop_reason": "tool_use",
            "usage": {
                "input_tokens": 11,
                "output_tokens": 7,
                "cache_read_input_tokens": 5,
                "cache_creation_input_tokens": 2,
            },
            "content": [
                {"type": "text", "text": "Sure."},
                {"type": "thinking", "thinking": "Need weather API", "signature": "sig_1"},
                {"type": "redacted_thinking", "data": "hidden"},
                {
                    "type": "tool_use",
                    "id": "call_1",
                    "name": "get_weather",
                    "input": {"city": "SF"},
                },
            ],
        }
        return httpx.Response(200, json=response_body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = AnthropicAdapter(api_key="test-key", http_client=client)

    request = Request(
        model="claude-sonnet-4-5-20250929",
        messages=[Message.user("weather?")],
        provider_options={"anthropic": {"beta_headers": ["reasoning-2025-01-01"]}},
    )
    response = await adapter.complete(request)

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/v1/messages")
    assert captured["headers"]["anthropic-beta"] == "reasoning-2025-01-01"
    assert captured["json"]["max_tokens"] == 4096
    assert response.finish_reason.reason == "tool_calls"
    assert response.usage.input_tokens == 11
    assert response.usage.output_tokens == 7
    assert response.usage.cache_read_tokens == 5
    assert response.usage.cache_write_tokens == 2
    assert response.message.content[0].kind == ContentKind.TEXT
    assert response.message.content[1].kind == ContentKind.THINKING
    assert response.message.content[2].kind == ContentKind.REDACTED_THINKING
    assert response.message.content[3].kind == ContentKind.TOOL_CALL

    await adapter.close()


@pytest.mark.asyncio
async def test_complete_maps_http_errors_with_retry_after_and_raw_body():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"retry-after": "3"},
            json={"error": {"message": "rate limit", "type": "rate_limit_error"}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = AnthropicAdapter(api_key="test-key", http_client=client)

    request = Request(model="claude-sonnet-4-5-20250929", messages=[Message.user("Hello")])

    with pytest.raises(RateLimitError) as excinfo:
        await adapter.complete(request)

    err = excinfo.value
    assert err.retry_after == 3.0
    assert err.raw == {"error": {"message": "rate limit", "type": "rate_limit_error"}}

    await adapter.close()


@pytest.mark.asyncio
async def test_stream_maps_text_reasoning_tool_events_and_finish():
    sse_lines = [
        "event: message_start\n"
        'data: {"type":"message_start","message":{"id":"msg_stream","model":"claude-sonnet-4-5-20250929","usage":{"input_tokens":3,"output_tokens":0}}}\n\n',
        "event: content_block_start\n"
        'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n',
        "event: content_block_delta\n"
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}\n\n',
        'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n',
        "event: content_block_start\n"
        'data: {"type":"content_block_start","index":1,"content_block":{"type":"thinking","thinking":""}}\n\n',
        "event: content_block_delta\n"
        'data: {"type":"content_block_delta","index":1,"delta":{"type":"thinking_delta","thinking":"Consider options"}}\n\n',
        'event: content_block_stop\ndata: {"type":"content_block_stop","index":1}\n\n',
        "event: content_block_start\n"
        'data: {"type":"content_block_start","index":2,"content_block":{"type":"tool_use","id":"call_1","name":"search","input":{}}}\n\n',
        "event: content_block_delta\n"
        'data: {"type":"content_block_delta","index":2,"delta":{"type":"input_json_delta","partial_json":"{\\"q\\":\\"mars\\"}"}}\n\n',
        'event: content_block_stop\ndata: {"type":"content_block_stop","index":2}\n\n',
        "event: message_delta\n"
        'data: {"type":"message_delta","delta":{"stop_reason":"tool_use"},"usage":{"output_tokens":8}}\n\n',
        'event: message_stop\ndata: {"type":"message_stop"}\n\n',
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content="".join(sse_lines).encode("utf-8"))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = AnthropicAdapter(api_key="test-key", http_client=client)

    request = Request(model="claude-sonnet-4-5-20250929", messages=[Message.user("Hello")])
    events = [event async for event in adapter.stream(request)]

    assert events[0].type == StreamEventType.TEXT_START
    assert events[1].type == StreamEventType.TEXT_DELTA
    assert events[1].delta == "Hello"
    assert events[3].type == StreamEventType.REASONING_START
    assert events[4].type == StreamEventType.REASONING_DELTA
    assert events[4].reasoning_delta == "Consider options"
    assert events[6].type == StreamEventType.TOOL_CALL_START
    assert events[7].type == StreamEventType.TOOL_CALL_DELTA
    assert events[8].type == StreamEventType.TOOL_CALL_END
    assert events[8].tool_call is not None
    assert events[8].tool_call.arguments == {"q": "mars"}
    assert events[-1].type == StreamEventType.FINISH
    assert events[-1].finish_reason.reason == "tool_calls"
    assert events[-1].usage.input_tokens == 3
    assert events[-1].usage.output_tokens == 8

    await adapter.close()
