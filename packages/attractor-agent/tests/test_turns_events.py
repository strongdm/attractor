from attractor_agent.events import EventEmitter, EventKind
from attractor_agent.turns import (
    AssistantTurn,
    SteeringTurn,
    SystemTurn,
    ToolResultsTurn,
    UserTurn,
)


def test_turn_dataclasses_basic_fields():
    user = UserTurn(content="hello")
    assistant = AssistantTurn(content="ok", tool_calls=[], usage=None)
    tool_results = ToolResultsTurn(results=[])
    system = SystemTurn(content="rules")
    steering = SteeringTurn(content="redirect")

    assert user.content == "hello"
    assert assistant.content == "ok"
    assert tool_results.results == []
    assert system.content == "rules"
    assert steering.content == "redirect"


def test_event_emitter_delivers_typed_events():
    emitter = EventEmitter()
    captured = []

    def subscriber(event):
        captured.append(event)

    emitter.subscribe(subscriber)
    event = emitter.emit(EventKind.USER_INPUT, session_id="s1", data={"content": "hi"})

    assert event.kind == EventKind.USER_INPUT
    assert event.session_id == "s1"
    assert captured[0] == event
