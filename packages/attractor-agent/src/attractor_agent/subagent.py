"""Subagent manager."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, Callable


class SubagentDepthError(ValueError):
    """Raised when spawning beyond configured depth."""


@dataclass
class SubAgentResult:
    output: str
    success: bool
    turns_used: int


@dataclass
class _SubagentHandle:
    id: str
    session: Any
    task: asyncio.Task | None
    status: str


class SubagentManager:
    def __init__(
        self,
        session_factory: Callable[[int], Any],
        max_depth: int,
        current_depth: int = 0,
    ):
        self._session_factory = session_factory
        self._max_depth = max_depth
        self._current_depth = current_depth
        self._agents: dict[str, _SubagentHandle] = {}

    async def spawn(self, task: str) -> str:
        if self._current_depth >= self._max_depth:
            raise SubagentDepthError("Maximum subagent depth reached")

        agent_id = str(uuid.uuid4())
        session = self._session_factory(self._current_depth + 1)
        run_task = asyncio.create_task(session.process_input(task))
        self._agents[agent_id] = _SubagentHandle(
            id=agent_id,
            session=session,
            task=run_task,
            status="running",
        )
        return agent_id

    async def send(self, agent_id: str, message: str) -> None:
        handle = self._get(agent_id)
        if handle.task is not None:
            await handle.task
        handle.task = asyncio.create_task(handle.session.process_input(message))
        handle.status = "running"

    async def wait(self, agent_id: str) -> SubAgentResult:
        handle = self._get(agent_id)
        success = True
        if handle.task is not None:
            try:
                await handle.task
            except Exception:
                success = False
        handle.status = "completed" if success else "failed"
        turns_used = len(getattr(handle.session, "history", []))
        output = ""
        if hasattr(handle.session, "last_assistant_text"):
            output = handle.session.last_assistant_text()
        return SubAgentResult(output=output, success=success, turns_used=turns_used)

    async def close(self, agent_id: str) -> str:
        handle = self._agents.pop(agent_id, None)
        if handle is None:
            return "already_closed"
        if handle.task is not None and not handle.task.done():
            handle.task.cancel()
            try:
                await handle.task
            except asyncio.CancelledError:
                pass
        return "closed"

    def _get(self, agent_id: str) -> _SubagentHandle:
        handle = self._agents.get(agent_id)
        if handle is None:
            raise ValueError(f"Unknown agent: {agent_id}")
        return handle
