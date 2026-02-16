"""Session state and orchestration entrypoints."""

from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from attractor_agent.events import EventEmitter
from attractor_agent.execution import LocalExecutionEnvironment
from attractor_agent.profiles.base import ProviderProfile
from attractor_agent.truncation import DEFAULT_TOOL_CHAR_LIMITS, DEFAULT_TOOL_LINE_LIMITS
from attractor_agent.turns import AssistantTurn, Turn


class SessionState(Enum):
    IDLE = "idle"
    PROCESSING = "processing"
    AWAITING_INPUT = "awaiting_input"
    CLOSED = "closed"


@dataclass
class SessionConfig:
    max_turns: int = 0
    max_tool_rounds_per_input: int = 0
    default_command_timeout_ms: int = 10_000
    max_command_timeout_ms: int = 600_000
    reasoning_effort: str | None = None
    tool_output_limits: dict[str, int] = field(
        default_factory=lambda: dict(DEFAULT_TOOL_CHAR_LIMITS)
    )
    tool_line_limits: dict[str, int] = field(
        default_factory=lambda: dict(DEFAULT_TOOL_LINE_LIMITS)
    )
    enable_loop_detection: bool = True
    loop_detection_window: int = 10
    max_subagent_depth: int = 1


@dataclass
class Session:
    provider_profile: ProviderProfile
    execution_env: LocalExecutionEnvironment
    llm_client: Any
    config: SessionConfig = field(default_factory=SessionConfig)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: SessionState = SessionState.IDLE
    history: list[Turn] = field(default_factory=list)
    events: EventEmitter = field(default_factory=EventEmitter)
    steering_queue: deque[str] = field(default_factory=deque)
    followup_queue: deque[str] = field(default_factory=deque)
    depth: int = 0

    def steer(self, message: str) -> None:
        self.steering_queue.append(message)

    def follow_up(self, message: str) -> None:
        self.followup_queue.append(message)

    async def process_input(self, user_input: str) -> None:
        from attractor_agent.loop import process_input

        await process_input(self, user_input)

    def last_assistant_text(self) -> str:
        for turn in reversed(self.history):
            if isinstance(turn, AssistantTurn):
                return turn.content
        return ""
