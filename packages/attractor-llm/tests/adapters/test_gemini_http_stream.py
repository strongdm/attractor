"""Tests for Gemini HTTP and streaming behavior."""

import json

import httpx
import pytest

from attractor_llm.adapters.gemini import GeminiAdapter
from attractor_llm.errors import RateLimitError
from attractor_llm.request import Request
from attractor_llm.response import StreamEventType
from attractor_llm.types import ContentKind, Message


@pytest.mark.asyncio
async def test_complete_posts_generate_content_and_maps_response():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["headers"] = dict(request.headers)
        captured["json"] = json.loads(request.content.decode("utf-8"))
        response_body = {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "role": "model",
                        "parts": [
                            {"text": "Sure."},
                            {
                                "functionCall": {
                                    "id": "call_1",
                                    "name": "get_weather",
                                    "args": {"city": "SF"},
                                }
                            },
                        ],
                    },
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 11,
                "candidatesTokenCount": 7,
                "thoughtsTokenCount": 3,
                "cachedContentTokenCount": 5,
            },
        }
        return httpx.Response(200, json=response_body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = GeminiAdapter(api_key="test-key", http_client=client)

    request = Request(model="gemini-2.5-pro", messages=[Message.user("weather?")])
    response = await adapter.complete(request)

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/v1beta/models/gemini-2.5-pro:generateContent?key=test-key")
    assert captured["headers"]["content-type"] == "application/json"
    assert captured["json"]["contents"] == [{"role": "user", "parts": [{"text": "weather?"}]}]
    assert response.finish_reason.reason == "tool_calls"
    assert response.usage.input_tokens == 11
    assert response.usage.output_tokens == 7
    assert response.usage.reasoning_tokens == 3
    assert response.usage.cache_read_tokens == 5
    assert response.message.content[0].kind == ContentKind.TEXT
    assert response.message.content[1].kind == ContentKind.TOOL_CALL

    await adapter.close()


@pytest.mark.asyncio
async def test_complete_maps_http_errors_with_retry_after_and_raw_body():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"retry-after": "3"},
            json={"error": {"message": "rate limit", "status": "RESOURCE_EXHAUSTED"}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = GeminiAdapter(api_key="test-key", http_client=client)

    request = Request(model="gemini-2.5-pro", messages=[Message.user("Hello")])

    with pytest.raises(RateLimitError) as excinfo:
        await adapter.complete(request)

    err = excinfo.value
    assert err.retry_after == 3.0
    assert err.raw == {"error": {"message": "rate limit", "status": "RESOURCE_EXHAUSTED"}}

    await adapter.close()


@pytest.mark.asyncio
async def test_stream_maps_text_tool_calls_and_finish_usage():
    sse_lines = [
        "event: message\n"
        'data: {"candidates":[{"content":{"role":"model","parts":[{"text":"Hel"}]}}]}\n\n',
        "event: message\n"
        'data: {"candidates":[{"content":{"role":"model","parts":[{"text":"lo"}]}}]}\n\n',
        "event: message\n"
        'data: {"candidates":[{"content":{"role":"model","parts":[{"functionCall":{"id":"call_1","name":"search","args":{"q":"mars"}}}]},"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":3,"candidatesTokenCount":8,"thoughtsTokenCount":2,"cachedContentTokenCount":1}}\n\n',
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content="".join(sse_lines).encode("utf-8"))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = GeminiAdapter(api_key="test-key", http_client=client)

    request = Request(model="gemini-2.5-pro", messages=[Message.user("Hello")])
    events = [event async for event in adapter.stream(request)]

    assert events[0].type == StreamEventType.TEXT_START
    assert events[1].type == StreamEventType.TEXT_DELTA
    assert events[1].delta == "Hel"
    assert events[2].type == StreamEventType.TEXT_DELTA
    assert events[2].delta == "lo"
    assert events[3].type == StreamEventType.TOOL_CALL_START
    assert events[4].type == StreamEventType.TOOL_CALL_END
    assert events[4].tool_call is not None
    assert events[4].tool_call.arguments == {"q": "mars"}
    assert events[-1].type == StreamEventType.FINISH
    assert events[-1].finish_reason is not None
    assert events[-1].finish_reason.reason == "tool_calls"
    assert events[-1].usage is not None
    assert events[-1].usage.input_tokens == 3
    assert events[-1].usage.output_tokens == 8
    assert events[-1].usage.reasoning_tokens == 2
    assert events[-1].usage.cache_read_tokens == 1

    await adapter.close()
