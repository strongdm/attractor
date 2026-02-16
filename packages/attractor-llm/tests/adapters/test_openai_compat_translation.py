"""Tests for OpenAI-compatible Chat Completions translation."""

from attractor_llm.adapters.openai_compat import OpenAICompatAdapter
from attractor_llm.request import Request, ToolChoice, ToolDefinition
from attractor_llm.types import ContentPart, Message, Role, ToolCallData


def test_translate_request_maps_chat_messages_tools_and_tool_choice():
    adapter = OpenAICompatAdapter(api_key="test-key")
    request = Request(
        model="gpt-4o-mini",
        messages=[
            Message.system("global safety"),
            Message(role=Role.DEVELOPER, content=[ContentPart.text("team style")]),
            Message.user("first"),
            Message(
                role=Role.ASSISTANT,
                content=[
                    ContentPart.text("Working on it."),
                    ContentPart.tool_call(
                        ToolCallData(
                            id="call_1",
                            name="get_weather",
                            arguments={"city": "SF"},
                        )
                    ),
                ],
            ),
            Message.tool_result("call_1", "Sunny"),
        ],
        tools=[
            ToolDefinition(
                name="get_weather",
                description="Get weather by city",
                parameters={
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            )
        ],
        tool_choice=ToolChoice(mode="named", tool_name="get_weather"),
    )

    payload = adapter._build_payload(request)

    assert payload["messages"] == [
        {"role": "system", "content": "global safety"},
        {"role": "developer", "content": "team style"},
        {"role": "user", "content": "first"},
        {
            "role": "assistant",
            "content": "Working on it.",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"city": "SF"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "Sunny",
        },
    ]
    assert payload["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather by city",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }
    ]
    assert payload["tool_choice"] == {
        "type": "function",
        "function": {"name": "get_weather"},
    }


def test_translate_tool_choice_modes():
    adapter = OpenAICompatAdapter(api_key="test-key")

    auto_payload = adapter._build_payload(
        Request(
            model="gpt-4o-mini",
            messages=[Message.user("Hello")],
            tool_choice=ToolChoice(mode="auto"),
        )
    )
    none_payload = adapter._build_payload(
        Request(
            model="gpt-4o-mini",
            messages=[Message.user("Hello")],
            tool_choice=ToolChoice(mode="none"),
        )
    )
    required_payload = adapter._build_payload(
        Request(
            model="gpt-4o-mini",
            messages=[Message.user("Hello")],
            tool_choice=ToolChoice(mode="required"),
        )
    )

    assert auto_payload["tool_choice"] == "auto"
    assert none_payload["tool_choice"] == "none"
    assert required_payload["tool_choice"] == "required"
