import pytest

from attractor_agent.subagent import SubagentDepthError, SubagentManager


class FakeSession:
    def __init__(self):
        self.received = []

    async def process_input(self, text: str):
        self.received.append(text)

    def last_assistant_text(self) -> str:
        return self.received[-1] if self.received else ""


async def test_subagent_manager_spawn_wait_send_close():
    manager = SubagentManager(session_factory=lambda _depth: FakeSession(), max_depth=1)

    agent_id = await manager.spawn("initial")
    await manager.send(agent_id, "follow up")
    result = await manager.wait(agent_id)

    assert result.success is True
    assert result.output == "follow up"

    closed = await manager.close(agent_id)
    assert closed in {"closed", "already_closed"}


async def test_subagent_manager_enforces_depth_limit():
    manager = SubagentManager(
        session_factory=lambda _depth: FakeSession(),
        max_depth=1,
        current_depth=1,
    )
    with pytest.raises(SubagentDepthError):
        await manager.spawn("x")
