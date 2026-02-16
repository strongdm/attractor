"""Server-Sent Events (SSE) parser for async streams."""

from __future__ import annotations

from typing import AsyncIterator


async def parse_sse_events(
    lines: AsyncIterator[str],
) -> AsyncIterator[tuple[str | None, str]]:
    """Parse an SSE stream, yielding (event_type, data) tuples.

    Follows the SSE specification:
    - Lines starting with ':' are comments (ignored)
    - 'event:' sets the event type for the next dispatch
    - 'data:' appends to the data buffer (multi-line supported)
    - Blank lines dispatch the accumulated event
    - '[DONE]' sentinel terminates the stream
    """
    event_type: str | None = None
    data_lines: list[str] = []

    async for line in lines:
        line = line.rstrip("\n\r")

        # Blank line = dispatch event
        if not line:
            if data_lines:
                data = "\n".join(data_lines)
                if data == "[DONE]":
                    return
                yield event_type, data
            # Reset state for next event
            event_type = None
            data_lines = []
            continue

        # Comment
        if line.startswith(":"):
            continue

        # Field parsing
        if ":" in line:
            field, _, value = line.partition(":")
            value = value.lstrip(" ")  # strip single leading space per spec
        else:
            field = line
            value = ""

        if field == "event":
            event_type = value
        elif field == "data":
            data_lines.append(value)
        # Ignore retry, id, and unknown fields
