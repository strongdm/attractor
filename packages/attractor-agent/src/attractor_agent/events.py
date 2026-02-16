"""Session event types and emitter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventKind(Enum):
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    USER_INPUT = "user_input"
    ASSISTANT_TEXT_START = "assistant_text_start"
    ASSISTANT_TEXT_DELTA = "assistant_text_delta"
    ASSISTANT_TEXT_END = "assistant_text_end"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_OUTPUT_DELTA = "tool_call_output_delta"
    TOOL_CALL_END = "tool_call_end"
    STEERING_INJECTED = "steering_injected"
    TURN_LIMIT = "turn_limit"
    LOOP_DETECTION = "loop_detection"
    ERROR = "error"


@dataclass
class SessionEvent:
    kind: EventKind
    session_id: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utcnow)


class EventEmitter:
    def __init__(self):
        self._subscribers: list[Callable[[SessionEvent], None]] = []

    def subscribe(self, callback: Callable[[SessionEvent], None]) -> None:
        self._subscribers.append(callback)

    def emit(
        self, kind: EventKind, session_id: str, data: dict[str, Any] | None = None
    ) -> SessionEvent:
        event = SessionEvent(kind=kind, session_id=session_id, data=data or {})
        for subscriber in list(self._subscribers):
            subscriber(event)
        return event
