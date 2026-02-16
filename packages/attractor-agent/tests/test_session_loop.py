from dataclasses import dataclass

from attractor_agent.events import EventKind
from attractor_agent.execution import LocalExecutionEnvironment
from attractor_agent.profiles.openai import create_openai_profile
from attractor_agent.session import Session, SessionConfig
from attractor_llm.request import Request
from attractor_llm.response import FinishReason, Response, Usage
from attractor_llm.types import ContentPart, Message, ToolCallData


@dataclass
class FakeClient:
    responses: list[Response]

    def __post_init__(self):
        self.requests: list[Request] = []

    async def complete(self, request: Request) -> Response:
        self.requests.append(request)
        return self.responses.pop(0)


def make_response(text: str, tool_calls: list[dict] | None = None) -> Response:
    content = [ContentPart.text(text)]
    for tc in tool_calls or []:
        content.append(
            ContentPart.tool_call(
                ToolCallData(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
            )
        )
    return Response(
        id="r1",
        model="test-model",
        provider="openai",
        message=Message(role=Message.assistant("").role, content=content),
        finish_reason=FinishReason(reason="stop"),
        usage=Usage(input_tokens=1, output_tokens=1),
    )


async def test_session_processes_simple_input(tmp_path):
    profile = create_openai_profile(model="gpt-test")
    client = FakeClient([make_response("done")])
    session = Session(
        provider_profile=profile,
        execution_env=LocalExecutionEnvironment(tmp_path),
        llm_client=client,
    )

    events = []
    session.events.subscribe(lambda e: events.append(e.kind))
    await session.process_input("hi")

    assert any(kind == EventKind.USER_INPUT for kind in events)
    assert session.last_assistant_text() == "done"


async def test_session_executes_tool_call_then_continues(tmp_path):
    profile = create_openai_profile(model="gpt-test")
    first = make_response(
        "running tool",
        [{"id": "t1", "name": "write_file", "arguments": {"file_path": "a.txt", "content": "ok"}}],
    )
    second = make_response("finished")
    client = FakeClient([first, second])
    session = Session(
        provider_profile=profile,
        execution_env=LocalExecutionEnvironment(tmp_path),
        llm_client=client,
    )

    await session.process_input("create file")

    assert (tmp_path / "a.txt").read_text() == "ok"
    assert session.last_assistant_text() == "finished"


async def test_session_steering_and_follow_up(tmp_path):
    profile = create_openai_profile(model="gpt-test")
    first = make_response("one")
    second = make_response("two")
    client = FakeClient([first, second])
    session = Session(
        provider_profile=profile,
        execution_env=LocalExecutionEnvironment(tmp_path),
        llm_client=client,
    )
    session.steer("keep it short")
    session.follow_up("and now summarize")

    await session.process_input("start")

    user_messages = [m for m in client.requests[0].messages if m.role.value == "user"]
    assert any("keep it short" in m.text for m in user_messages)
    assert len(client.requests) == 2
    assert session.last_assistant_text() == "two"


async def test_session_loop_detection_injects_warning(tmp_path):
    profile = create_openai_profile(model="gpt-test")
    tool_call = {"id": "t1", "name": "glob", "arguments": {"pattern": "*.py"}}
    responses = [
        make_response("loop", [tool_call]),
        make_response("loop", [tool_call]),
        make_response("loop", [tool_call]),
        make_response("done"),
    ]
    client = FakeClient(responses)
    session = Session(
        provider_profile=profile,
        execution_env=LocalExecutionEnvironment(tmp_path),
        llm_client=client,
        config=SessionConfig(loop_detection_window=3),
    )

    await session.process_input("go")

    assert any(
        "Loop detected" in turn.content for turn in session.history if hasattr(turn, "content")
    )
