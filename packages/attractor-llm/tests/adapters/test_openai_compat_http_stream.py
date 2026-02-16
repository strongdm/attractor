"""Tests for OpenAI-compatible Chat Completions HTTP and stream behavior."""

import json

import httpx
import pytest

from attractor_llm.adapters.openai_compat import OpenAICompatAdapter
from attractor_llm.errors import RateLimitError
from attractor_llm.request import Request
from attractor_llm.response import StreamEventType
from attractor_llm.types import ContentKind, Message


@pytest.mark.asyncio
async def test_complete_posts_chat_completions_and_maps_response():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["headers"] = dict(request.headers)
        captured["json"] = json.loads(request.content.decode("utf-8"))
        response_body = {
            "id": "chatcmpl_1",
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "Sure.",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "get_weather",
                                    "arguments": '{"city":"SF"}',
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "completion_tokens_details": {"reasoning_tokens": 3},
            },
        }
        return httpx.Response(200, json=response_body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OpenAICompatAdapter(api_key="test-key", http_client=client)

    request = Request(model="gpt-4o-mini", messages=[Message.user("weather?")])
    response = await adapter.complete(request)

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/v1/chat/completions")
    assert captured["headers"]["authorization"] == "Bearer test-key"
    assert captured["json"]["model"] == "gpt-4o-mini"
    assert response.finish_reason.reason == "tool_calls"
    assert response.usage.input_tokens == 11
    assert response.usage.output_tokens == 7
    assert response.usage.reasoning_tokens == 3
    assert response.message.content[0].kind == ContentKind.TEXT
    assert response.message.content[1].kind == ContentKind.TOOL_CALL

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
    adapter = OpenAICompatAdapter(api_key="test-key", http_client=client)

    request = Request(model="gpt-4o-mini", messages=[Message.user("Hello")])

    with pytest.raises(RateLimitError) as excinfo:
        await adapter.complete(request)

    err = excinfo.value
    assert err.retry_after == 3.0
    assert err.raw == {"error": {"message": "rate limit", "type": "rate_limit_error"}}

    await adapter.close()


@pytest.mark.asyncio
async def test_stream_maps_text_tool_call_delta_end_and_finish_usage():
    sse_lines = [
        'data: {"id":"chatcmpl_1","model":"gpt-4o-mini","choices":[{"index":0,"delta":{"role":"assistant","content":"Hello"},"finish_reason":null}]}\n\n',
        'data: {"id":"chatcmpl_1","model":"gpt-4o-mini","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"search","arguments":"{\\"q\\":"}}]},"finish_reason":null}]}\n\n',
        'data: {"id":"chatcmpl_1","model":"gpt-4o-mini","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"mars\\"}"}}]},"finish_reason":null}]}\n\n',
        'data: {"id":"chatcmpl_1","model":"gpt-4o-mini","choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":3,"completion_tokens":8,"completion_tokens_details":{"reasoning_tokens":2}}}\n\n',
        "data: [DONE]\n\n",
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content="".join(sse_lines).encode("utf-8"))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OpenAICompatAdapter(api_key="test-key", http_client=client)

    request = Request(model="gpt-4o-mini", messages=[Message.user("Hello")])
    events = [event async for event in adapter.stream(request)]

    assert events[0].type == StreamEventType.TEXT_START
    assert events[1].type == StreamEventType.TEXT_DELTA
    assert events[1].delta == "Hello"
    assert events[2].type == StreamEventType.TOOL_CALL_START
    assert events[3].type == StreamEventType.TOOL_CALL_DELTA
    assert events[4].type == StreamEventType.TOOL_CALL_DELTA
    assert events[5].type == StreamEventType.TEXT_END
    assert events[6].type == StreamEventType.TOOL_CALL_END
    assert events[6].tool_call is not None
    assert events[6].tool_call.arguments == {"q": "mars"}
    assert events[-1].type == StreamEventType.FINISH
    assert events[-1].usage is not None
    assert events[-1].usage.input_tokens == 3
    assert events[-1].usage.output_tokens == 8
    assert events[-1].usage.reasoning_tokens == 2

    await adapter.close()
