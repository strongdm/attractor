"""Tests for Response, FinishReason, Usage, ToolCall, ToolResult, StreamEvent."""

from attractor_llm.response import (
    FinishReason,
    RateLimitInfo,
    Response,
    StreamEvent,
    StreamEventType,
    ToolCall,
    ToolResult,
    Usage,
    Warning,
)
from attractor_llm.types import ContentKind, ContentPart, Message, Role, ToolCallData


class TestFinishReason:
    def test_stop(self):
        fr = FinishReason(reason="stop")
        assert fr.reason == "stop"
        assert fr.raw is None

    def test_with_raw(self):
        fr = FinishReason(reason="stop", raw="end_turn")
        assert fr.raw == "end_turn"

    def test_tool_calls(self):
        fr = FinishReason(reason="tool_calls")
        assert fr.reason == "tool_calls"


class TestUsage:
    def test_basic_usage(self):
        u = Usage(input_tokens=100, output_tokens=50)
        assert u.input_tokens == 100
        assert u.output_tokens == 50
        assert u.total_tokens == 150

    def test_total_tokens_property(self):
        u = Usage(input_tokens=200, output_tokens=100)
        assert u.total_tokens == 300

    def test_optional_fields_default_none(self):
        u = Usage(input_tokens=10, output_tokens=5)
        assert u.reasoning_tokens is None
        assert u.cache_read_tokens is None
        assert u.cache_write_tokens is None

    def test_addition_both_present(self):
        a = Usage(input_tokens=100, output_tokens=50, reasoning_tokens=10)
        b = Usage(input_tokens=200, output_tokens=100, reasoning_tokens=20)
        c = a + b
        assert c.input_tokens == 300
        assert c.output_tokens == 150
        assert c.total_tokens == 450
        assert c.reasoning_tokens == 30

    def test_addition_one_none(self):
        """When one side has None for an optional field, treat as 0."""
        a = Usage(input_tokens=100, output_tokens=50, reasoning_tokens=10)
        b = Usage(input_tokens=200, output_tokens=100, reasoning_tokens=None)
        c = a + b
        assert c.reasoning_tokens == 10

    def test_addition_both_none(self):
        """When both sides have None, result is None."""
        a = Usage(input_tokens=100, output_tokens=50)
        b = Usage(input_tokens=200, output_tokens=100)
        c = a + b
        assert c.reasoning_tokens is None

    def test_addition_cache_tokens(self):
        a = Usage(input_tokens=100, output_tokens=50, cache_read_tokens=30, cache_write_tokens=10)
        b = Usage(input_tokens=200, output_tokens=100, cache_read_tokens=20)
        c = a + b
        assert c.cache_read_tokens == 50
        assert c.cache_write_tokens == 10

    def test_with_raw(self):
        u = Usage(input_tokens=10, output_tokens=5, raw={"custom": "data"})
        assert u.raw == {"custom": "data"}


class TestToolCall:
    def test_basic(self):
        tc = ToolCall(
            id="call_123",
            name="get_weather",
            arguments={"location": "SF"},
        )
        assert tc.id == "call_123"
        assert tc.name == "get_weather"
        assert tc.arguments == {"location": "SF"}
        assert tc.raw_arguments is None

    def test_with_raw_arguments(self):
        tc = ToolCall(
            id="call_123",
            name="search",
            arguments={"q": "hello"},
            raw_arguments='{"q": "hello"}',
        )
        assert tc.raw_arguments == '{"q": "hello"}'


class TestToolResult:
    def test_success(self):
        tr = ToolResult(
            tool_call_id="call_123",
            content="Sunny, 72F",
        )
        assert tr.is_error is False

    def test_error(self):
        tr = ToolResult(
            tool_call_id="call_123",
            content="Connection failed",
            is_error=True,
        )
        assert tr.is_error is True

    def test_dict_content(self):
        tr = ToolResult(
            tool_call_id="call_123",
            content={"temp": 72, "condition": "sunny"},
        )
        assert tr.content["temp"] == 72


class TestWarning:
    def test_basic(self):
        w = Warning(message="Something happened")
        assert w.message == "Something happened"
        assert w.code is None

    def test_with_code(self):
        w = Warning(message="Rate limited", code="rate_limit_warning")
        assert w.code == "rate_limit_warning"


class TestRateLimitInfo:
    def test_basic(self):
        rli = RateLimitInfo(
            requests_remaining=100,
            requests_limit=1000,
        )
        assert rli.requests_remaining == 100
        assert rli.tokens_remaining is None


class TestResponse:
    def test_basic_response(self):
        msg = Message.assistant("Hello!")
        resp = Response(
            id="resp_123",
            model="claude-opus-4-6",
            provider="anthropic",
            message=msg,
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=10, output_tokens=5),
        )
        assert resp.id == "resp_123"
        assert resp.text == "Hello!"
        assert resp.finish_reason.reason == "stop"

    def test_text_property(self):
        msg = Message.assistant("Hello world")
        resp = Response(
            id="r1",
            model="m",
            provider="p",
            message=msg,
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=0, output_tokens=0),
        )
        assert resp.text == "Hello world"

    def test_tool_calls_property(self):
        tc_data = ToolCallData(id="call_1", name="search", arguments={"q": "hi"})
        msg = Message(
            role=Role.ASSISTANT,
            content=[
                ContentPart.text("Let me search for that."),
                ContentPart.tool_call(tc_data),
            ],
        )
        resp = Response(
            id="r1",
            model="m",
            provider="p",
            message=msg,
            finish_reason=FinishReason(reason="tool_calls"),
            usage=Usage(input_tokens=0, output_tokens=0),
        )
        tool_calls = resp.tool_calls
        assert len(tool_calls) == 1
        assert tool_calls[0].id == "call_1"
        assert tool_calls[0].name == "search"

    def test_reasoning_property(self):
        from attractor_llm.types import ThinkingData

        msg = Message(
            role=Role.ASSISTANT,
            content=[
                ContentPart.thinking(ThinkingData(text="Let me think...")),
                ContentPart.text("The answer is 42."),
            ],
        )
        resp = Response(
            id="r1",
            model="m",
            provider="p",
            message=msg,
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=0, output_tokens=0),
        )
        assert resp.reasoning == "Let me think..."

    def test_reasoning_property_none_when_no_thinking(self):
        msg = Message.assistant("Just text")
        resp = Response(
            id="r1",
            model="m",
            provider="p",
            message=msg,
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=0, output_tokens=0),
        )
        assert resp.reasoning is None

    def test_raw_and_warnings(self):
        msg = Message.assistant("ok")
        resp = Response(
            id="r1",
            model="m",
            provider="p",
            message=msg,
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=0, output_tokens=0),
            raw={"original": "data"},
            warnings=[Warning(message="heads up")],
        )
        assert resp.raw == {"original": "data"}
        assert len(resp.warnings) == 1


class TestStreamEventType:
    def test_all_types_exist(self):
        assert StreamEventType.STREAM_START
        assert StreamEventType.TEXT_START
        assert StreamEventType.TEXT_DELTA
        assert StreamEventType.TEXT_END
        assert StreamEventType.REASONING_START
        assert StreamEventType.REASONING_DELTA
        assert StreamEventType.REASONING_END
        assert StreamEventType.TOOL_CALL_START
        assert StreamEventType.TOOL_CALL_DELTA
        assert StreamEventType.TOOL_CALL_END
        assert StreamEventType.FINISH
        assert StreamEventType.ERROR
        assert StreamEventType.PROVIDER_EVENT


class TestStreamEvent:
    def test_text_delta(self):
        evt = StreamEvent(
            type=StreamEventType.TEXT_DELTA,
            delta="Hello ",
            text_id="txt_0",
        )
        assert evt.type == StreamEventType.TEXT_DELTA
        assert evt.delta == "Hello "
        assert evt.text_id == "txt_0"

    def test_finish_event(self):
        evt = StreamEvent(
            type=StreamEventType.FINISH,
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=10, output_tokens=5),
        )
        assert evt.finish_reason.reason == "stop"
        assert evt.usage.total_tokens == 15

    def test_error_event(self):
        evt = StreamEvent(
            type=StreamEventType.ERROR,
            error=RuntimeError("stream broke"),
        )
        assert evt.error is not None

    def test_tool_call_start(self):
        tc = ToolCall(id="call_1", name="search", arguments={})
        evt = StreamEvent(
            type=StreamEventType.TOOL_CALL_START,
            tool_call=tc,
        )
        assert evt.tool_call.name == "search"
