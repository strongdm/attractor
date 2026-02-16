"""Tests for OpenAI Responses HTTP and streaming behavior."""

import json

import httpx
import pytest

from attractor_llm.adapters.openai import OpenAIAdapter
from attractor_llm.errors import RateLimitError
from attractor_llm.request import Request
from attractor_llm.response import StreamEventType
from attractor_llm.types import ContentKind, Message


@pytest.mark.asyncio
async def test_complete_posts_responses_and_maps_text_tool_calls_usage():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["headers"] = dict(request.headers)
        captured["json"] = json.loads(request.content.decode("utf-8"))
        response_body = {
            "id": "resp_1",
            "model": "gpt-5-mini",
            "status": "completed",
            "usage": {
                "input_tokens": 11,
                "output_tokens": 7,
                "output_tokens_details": {"reasoning_tokens": 3},
                "input_tokens_details": {"cached_tokens": 5},
            },
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Sure."}],
                },
                {
                    "type": "function_call",
                    "id": "fc_1",
                    "call_id": "call_1",
                    "name": "get_weather",
                    "arguments": '{"city":"SF"}',
                },
            ],
        }
        return httpx.Response(200, json=response_body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OpenAIAdapter(api_key="test-key", http_client=client)

    request = Request(model="gpt-5-mini", messages=[Message.user("weather?")])
    response = await adapter.complete(request)

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/v1/responses")
    assert captured["headers"]["authorization"] == "Bearer test-key"
    assert captured["json"]["model"] == "gpt-5-mini"
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
            json={"error": {"message": "rate limit", "type": "rate_limit_error"}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OpenAIAdapter(api_key="test-key", http_client=client)

    request = Request(model="gpt-5-mini", messages=[Message.user("Hello")])

    with pytest.raises(RateLimitError) as excinfo:
        await adapter.complete(request)

    err = excinfo.value
    assert err.retry_after == 3.0
    assert err.raw == {"error": {"message": "rate limit", "type": "rate_limit_error"}}

    await adapter.close()


@pytest.mark.asyncio
async def test_stream_maps_text_tool_call_and_finish_usage():
    sse_lines = [
        "event: response.output_item.added\n"
        'data: {"type":"response.output_item.added","output_index":0,"item":{"id":"msg_1","type":"message","role":"assistant"}}\n\n',
        "event: response.output_text.delta\n"
        'data: {"type":"response.output_text.delta","output_index":0,"content_index":0,"delta":"Hello"}\n\n',
        "event: response.output_text.done\n"
        'data: {"type":"response.output_text.done","output_index":0,"content_index":0,"text":"Hello"}\n\n',
        "event: response.output_item.added\n"
        'data: {"type":"response.output_item.added","output_index":1,"item":{"type":"function_call","id":"fc_1","call_id":"call_1","name":"search","arguments":""}}\n\n',
        "event: response.function_call_arguments.delta\n"
        'data: {"type":"response.function_call_arguments.delta","output_index":1,"delta":"{\\"q\\":\\"mars\\"}"}\n\n',
        "event: response.function_call_arguments.done\n"
        'data: {"type":"response.function_call_arguments.done","output_index":1,"arguments":"{\\"q\\":\\"mars\\"}"}\n\n',
        "event: response.completed\n"
        'data: {"type":"response.completed","response":{"id":"resp_1","model":"gpt-5-mini","status":"completed","usage":{"input_tokens":3,"output_tokens":8,"output_tokens_details":{"reasoning_tokens":2},"input_tokens_details":{"cached_tokens":1}},"output":[{"type":"message","role":"assistant","content":[{"type":"output_text","text":"Hello"}]},{"type":"function_call","id":"fc_1","call_id":"call_1","name":"search","arguments":"{\\"q\\":\\"mars\\"}"}]}}\n\n',
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content="".join(sse_lines).encode("utf-8"))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OpenAIAdapter(api_key="test-key", http_client=client)

    request = Request(model="gpt-5-mini", messages=[Message.user("Hello")])
    events = [event async for event in adapter.stream(request)]

    assert events[0].type == StreamEventType.TEXT_START
    assert events[1].type == StreamEventType.TEXT_DELTA
    assert events[1].delta == "Hello"
    assert events[2].type == StreamEventType.TEXT_END
    assert events[3].type == StreamEventType.TOOL_CALL_START
    assert events[4].type == StreamEventType.TOOL_CALL_DELTA
    assert events[5].type == StreamEventType.TOOL_CALL_END
    assert events[5].tool_call is not None
    assert events[5].tool_call.arguments == {"q": "mars"}
    assert events[-1].type == StreamEventType.FINISH
    assert events[-1].usage is not None
    assert events[-1].usage.input_tokens == 3
    assert events[-1].usage.output_tokens == 8
    assert events[-1].usage.reasoning_tokens == 2
    assert events[-1].usage.cache_read_tokens == 1

    await adapter.close()
