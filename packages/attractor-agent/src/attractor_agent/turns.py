"""Conversation turn dataclasses for agent sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from attractor_llm.response import ToolCall, ToolResult, Usage


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class UserTurn:
    content: str
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass
class AssistantTurn:
    content: str
    tool_calls: list[ToolCall]
    reasoning: str | None = None
    usage: Usage | None = None
    response_id: str | None = None
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass
class ToolResultsTurn:
    results: list[ToolResult]
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass
class SystemTurn:
    content: str
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass
class SteeringTurn:
    content: str
    timestamp: datetime = field(default_factory=_utcnow)


Turn = UserTurn | AssistantTurn | ToolResultsTurn | SystemTurn | SteeringTurn
