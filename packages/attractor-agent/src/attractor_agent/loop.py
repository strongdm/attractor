"""Core agent loop implementation."""

from __future__ import annotations

import json

from attractor_agent.events import EventKind
from attractor_agent.session import SessionState
from attractor_agent.truncation import truncate_tool_output
from attractor_agent.turns import (
    AssistantTurn,
    SteeringTurn,
    SystemTurn,
    ToolResultsTurn,
    UserTurn,
)
from attractor_llm.request import Request, ToolChoice
from attractor_llm.response import ToolResult
from attractor_llm.types import ContentPart, Message, Role, ToolCallData


def convert_history_to_messages(history: list) -> list[Message]:
    messages: list[Message] = []
    for turn in history:
        if isinstance(turn, (UserTurn, SteeringTurn)):
            messages.append(Message.user(turn.content))
        elif isinstance(turn, SystemTurn):
            messages.append(Message.system(turn.content))
        elif isinstance(turn, AssistantTurn):
            content = [ContentPart.text(turn.content)]
            for tc in turn.tool_calls:
                content.append(
                    ContentPart.tool_call(
                        ToolCallData(id=tc.id, name=tc.name, arguments=tc.arguments)
                    )
                )
            messages.append(Message(role=Role.ASSISTANT, content=content))
        elif isinstance(turn, ToolResultsTurn):
            for result in turn.results:
                messages.append(
                    Message.tool_result(
                        tool_call_id=result.tool_call_id,
                        content=result.content
                        if isinstance(result.content, str)
                        else str(result.content),
                        is_error=result.is_error,
                    )
                )
    return messages


def _drain_steering(session) -> None:
    while session.steering_queue:
        message = session.steering_queue.popleft()
        session.history.append(SteeringTurn(content=message))
        session.events.emit(EventKind.STEERING_INJECTED, session.id, {"content": message})


def detect_loop(history: list, window_size: int) -> bool:
    signatures = []
    for turn in history:
        if isinstance(turn, AssistantTurn):
            for call in turn.tool_calls:
                key = json.dumps(call.arguments, sort_keys=True)
                signatures.append(f"{call.name}:{key}")

    if len(signatures) < window_size:
        return False

    recent = signatures[-window_size:]
    for pattern_len in [1, 2, 3]:
        if window_size % pattern_len != 0:
            continue
        pattern = recent[:pattern_len]
        if all(recent[i : i + pattern_len] == pattern for i in range(0, window_size, pattern_len)):
            return True
    return False


async def execute_single_tool(session, tool_call) -> ToolResult:
    session.events.emit(
        EventKind.TOOL_CALL_START,
        session.id,
        {"tool_name": tool_call.name, "call_id": tool_call.id},
    )
    try:
        raw = await session.provider_profile.tool_registry.execute(
            tool_call.name,
            tool_call.arguments,
            session.execution_env,
        )
        truncated = truncate_tool_output(
            raw,
            tool_call.name,
            tool_char_limits=session.config.tool_output_limits,
            tool_line_limits=session.config.tool_line_limits,
        )
        session.events.emit(
            EventKind.TOOL_CALL_END,
            session.id,
            {"tool_name": tool_call.name, "call_id": tool_call.id, "output": raw},
        )
        return ToolResult(tool_call_id=tool_call.id, content=truncated, is_error=False)
    except Exception as error:
        message = f"Tool error ({tool_call.name}): {error}"
        session.events.emit(
            EventKind.TOOL_CALL_END,
            session.id,
            {"tool_name": tool_call.name, "call_id": tool_call.id, "error": message},
        )
        return ToolResult(tool_call_id=tool_call.id, content=message, is_error=True)


async def execute_tool_calls(session, tool_calls) -> list[ToolResult]:
    results = []
    for tool_call in tool_calls:
        result = await execute_single_tool(session, tool_call)
        results.append(result)
    return results


async def process_input(session, user_input: str) -> None:
    session.state = SessionState.PROCESSING
    session.history.append(UserTurn(content=user_input))
    session.events.emit(EventKind.USER_INPUT, session.id, {"content": user_input})
    _drain_steering(session)

    round_count = 0
    while True:
        if session.config.max_tool_rounds_per_input > 0:
            if round_count >= session.config.max_tool_rounds_per_input:
                session.events.emit(EventKind.TURN_LIMIT, session.id, {"round": round_count})
                break
        if session.config.max_turns > 0 and len(session.history) >= session.config.max_turns:
            session.events.emit(
                EventKind.TURN_LIMIT, session.id, {"total_turns": len(session.history)}
            )
            break

        messages = [Message.system(session.provider_profile.build_system_prompt())]
        messages.extend(convert_history_to_messages(session.history))
        request = Request(
            model=session.provider_profile.model,
            provider=session.provider_profile.provider_name,
            messages=messages,
            tools=session.provider_profile.tools(),
            tool_choice=ToolChoice(mode="auto"),
            reasoning_effort=session.config.reasoning_effort,
            provider_options=session.provider_profile.provider_options(),
        )
        response = await session.llm_client.complete(request)

        assistant_turn = AssistantTurn(
            content=response.text,
            tool_calls=response.tool_calls,
            reasoning=response.reasoning,
            usage=response.usage,
            response_id=response.id,
        )
        session.history.append(assistant_turn)
        session.events.emit(
            EventKind.ASSISTANT_TEXT_END,
            session.id,
            {"text": response.text, "reasoning": response.reasoning},
        )

        if not response.tool_calls:
            break

        round_count += 1
        results = await execute_tool_calls(session, response.tool_calls)
        session.history.append(ToolResultsTurn(results=results))
        _drain_steering(session)

        if session.config.enable_loop_detection:
            if detect_loop(session.history, session.config.loop_detection_window):
                warning = (
                    "Loop detected: the last tool calls follow a repeating pattern. "
                    "Try a different approach."
                )
                session.history.append(SteeringTurn(content=warning))
                session.events.emit(EventKind.LOOP_DETECTION, session.id, {"message": warning})

    session.state = SessionState.IDLE
    session.events.emit(EventKind.SESSION_END, session.id, {})

    while session.followup_queue:
        next_input = session.followup_queue.popleft()
        await process_input(session, next_input)
