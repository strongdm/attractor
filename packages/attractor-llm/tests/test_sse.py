"""Tests for the SSE (Server-Sent Events) parser."""

import pytest

from attractor_llm.sse import parse_sse_events


def _lines_to_bytes(lines: list[str]) -> list[bytes]:
    """Convert lines to bytes as they'd come from an HTTP stream."""
    return [line.encode("utf-8") for line in lines]


class TestParseSSE:
    async def test_simple_data_event(self):
        lines = [
            "data: hello world\n",
            "\n",
        ]
        events = []
        async for event_type, data in parse_sse_events(_async_iter(lines)):
            events.append((event_type, data))
        assert events == [(None, "hello world")]

    async def test_typed_event(self):
        lines = [
            "event: message\n",
            "data: hello\n",
            "\n",
        ]
        events = []
        async for event_type, data in parse_sse_events(_async_iter(lines)):
            events.append((event_type, data))
        assert events == [("message", "hello")]

    async def test_multi_line_data(self):
        lines = [
            "data: line one\n",
            "data: line two\n",
            "\n",
        ]
        events = []
        async for event_type, data in parse_sse_events(_async_iter(lines)):
            events.append((event_type, data))
        assert events == [(None, "line one\nline two")]

    async def test_comments_ignored(self):
        lines = [
            ": this is a comment\n",
            "data: actual data\n",
            "\n",
        ]
        events = []
        async for event_type, data in parse_sse_events(_async_iter(lines)):
            events.append((event_type, data))
        assert events == [(None, "actual data")]

    async def test_multiple_events(self):
        lines = [
            "event: start\n",
            "data: first\n",
            "\n",
            "event: delta\n",
            "data: second\n",
            "\n",
        ]
        events = []
        async for event_type, data in parse_sse_events(_async_iter(lines)):
            events.append((event_type, data))
        assert events == [("start", "first"), ("delta", "second")]

    async def test_done_sentinel_stops(self):
        """[DONE] sentinel should end the stream."""
        lines = [
            "data: hello\n",
            "\n",
            "data: [DONE]\n",
            "\n",
            "data: should not see this\n",
            "\n",
        ]
        events = []
        async for event_type, data in parse_sse_events(_async_iter(lines)):
            events.append((event_type, data))
        assert events == [(None, "hello")]

    async def test_empty_data(self):
        lines = [
            "data: \n",
            "\n",
        ]
        events = []
        async for event_type, data in parse_sse_events(_async_iter(lines)):
            events.append((event_type, data))
        assert events == [(None, "")]

    async def test_event_type_reset_between_events(self):
        lines = [
            "event: custom\n",
            "data: first\n",
            "\n",
            "data: second\n",
            "\n",
        ]
        events = []
        async for event_type, data in parse_sse_events(_async_iter(lines)):
            events.append((event_type, data))
        assert events == [("custom", "first"), (None, "second")]

    async def test_no_data_event_skipped(self):
        """Events with no data lines are skipped."""
        lines = [
            "event: ping\n",
            "\n",
            "data: real data\n",
            "\n",
        ]
        events = []
        async for event_type, data in parse_sse_events(_async_iter(lines)):
            events.append((event_type, data))
        assert events == [(None, "real data")]

    async def test_json_data(self):
        lines = [
            'data: {"key": "value", "num": 42}\n',
            "\n",
        ]
        events = []
        async for event_type, data in parse_sse_events(_async_iter(lines)):
            events.append((event_type, data))
        assert events == [(None, '{"key": "value", "num": 42}')]


async def _async_iter(lines: list[str]):
    """Create an async iterator from a list of strings (simulating httpx stream)."""
    for line in lines:
        yield line
