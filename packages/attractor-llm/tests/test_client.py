"""Tests for ProviderAdapter interface and Client core."""

import pytest

from attractor_llm.adapters.base import ProviderAdapter
from attractor_llm.client import Client, get_default_client, set_default_client
from attractor_llm.errors import ConfigurationError
from attractor_llm.request import Request
from attractor_llm.response import (
    FinishReason,
    Response,
    StreamEvent,
    StreamEventType,
    Usage,
)
from attractor_llm.types import Message, Role


class FakeAdapter(ProviderAdapter):
    """Minimal adapter for testing."""

    def __init__(self, name: str = "fake"):
        self._name = name
        self.complete_calls: list[Request] = []

    @property
    def name(self) -> str:
        return self._name

    async def complete(self, request: Request) -> Response:
        self.complete_calls.append(request)
        return Response(
            id="resp_fake",
            model=request.model,
            provider=self._name,
            message=Message.assistant(f"Response from {self._name}"),
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=10, output_tokens=5),
        )

    async def stream(self, request: Request):
        yield StreamEvent(type=StreamEventType.TEXT_DELTA, delta="hello")
        yield StreamEvent(
            type=StreamEventType.FINISH,
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=10, output_tokens=5),
        )


class TestProviderAdapter:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            ProviderAdapter()  # type: ignore


class TestClientRouting:
    async def test_explicit_provider(self):
        adapter_a = FakeAdapter("alpha")
        adapter_b = FakeAdapter("beta")
        client = Client(providers={"alpha": adapter_a, "beta": adapter_b})

        req = Request(model="test-model", messages=[Message.user("hi")], provider="beta")
        resp = await client.complete(req)
        assert resp.provider == "beta"
        assert len(adapter_b.complete_calls) == 1
        assert len(adapter_a.complete_calls) == 0

    async def test_default_provider(self):
        adapter = FakeAdapter("default")
        client = Client(providers={"default": adapter}, default_provider="default")

        req = Request(model="test-model", messages=[Message.user("hi")])
        resp = await client.complete(req)
        assert resp.provider == "default"

    async def test_single_provider_auto_default(self):
        adapter = FakeAdapter("only")
        client = Client(providers={"only": adapter})

        req = Request(model="test-model", messages=[Message.user("hi")])
        resp = await client.complete(req)
        assert resp.provider == "only"

    async def test_missing_provider_raises(self):
        client = Client(providers={"a": FakeAdapter("a")})
        req = Request(model="m", messages=[Message.user("hi")], provider="nonexistent")
        with pytest.raises(ConfigurationError, match="Unknown provider"):
            await client.complete(req)

    async def test_ambiguous_no_default_raises(self):
        client = Client(providers={"a": FakeAdapter("a"), "b": FakeAdapter("b")})
        req = Request(model="m", messages=[Message.user("hi")])
        with pytest.raises(ConfigurationError, match="No provider specified"):
            await client.complete(req)

    async def test_streaming(self):
        adapter = FakeAdapter("s")
        client = Client(providers={"s": adapter}, default_provider="s")

        req = Request(model="m", messages=[Message.user("hi")])
        events = []
        async for event in client.stream(req):
            events.append(event)
        assert len(events) == 2
        assert events[0].type == StreamEventType.TEXT_DELTA
        assert events[1].type == StreamEventType.FINISH


class TestMiddleware:
    async def test_middleware_request_order(self):
        """Middleware executes in registration order on request path."""
        order = []

        async def mw_a(request, next_fn):
            order.append("a_before")
            response = await next_fn(request)
            order.append("a_after")
            return response

        async def mw_b(request, next_fn):
            order.append("b_before")
            response = await next_fn(request)
            order.append("b_after")
            return response

        adapter = FakeAdapter("test")
        client = Client(
            providers={"test": adapter},
            default_provider="test",
            middleware=[mw_a, mw_b],
        )

        req = Request(model="m", messages=[Message.user("hi")])
        await client.complete(req)

        assert order == ["a_before", "b_before", "b_after", "a_after"]

    async def test_middleware_can_modify_request(self):
        async def add_metadata(request, next_fn):
            request.metadata = {"injected": "true"}
            return await next_fn(request)

        adapter = FakeAdapter("test")
        client = Client(
            providers={"test": adapter},
            default_provider="test",
            middleware=[add_metadata],
        )

        req = Request(model="m", messages=[Message.user("hi")])
        await client.complete(req)

        assert adapter.complete_calls[0].metadata == {"injected": "true"}

    async def test_middleware_streaming(self):
        """Middleware can wrap streaming events."""
        seen_events = []

        async def logging_mw(request, next_fn):
            async for event in next_fn(request):
                seen_events.append(event.type)
                yield event

        adapter = FakeAdapter("test")
        client = Client(
            providers={"test": adapter},
            default_provider="test",
            middleware=[logging_mw],
        )

        req = Request(model="m", messages=[Message.user("hi")])
        events = []
        async for event in client.stream(req):
            events.append(event)

        assert len(events) == 2
        assert seen_events == [StreamEventType.TEXT_DELTA, StreamEventType.FINISH]


class TestDefaultClient:
    def test_set_and_get(self):
        adapter = FakeAdapter("test")
        client = Client(providers={"test": adapter})
        set_default_client(client)
        assert get_default_client() is client
        # Clean up
        set_default_client(None)

    def test_get_unset_returns_none(self):
        set_default_client(None)
        assert get_default_client() is None
