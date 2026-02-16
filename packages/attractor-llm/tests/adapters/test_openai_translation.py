"""Tests for OpenAI Responses request translation."""

from attractor_llm.adapters.openai import OpenAIAdapter
from attractor_llm.request import Request, ResponseFormat, ToolChoice, ToolDefinition
from attractor_llm.types import ContentPart, Message, Role, ToolCallData


def test_translate_request_maps_messages_tools_and_options():
    adapter = OpenAIAdapter(api_key="test-key")
    request = Request(
        model="gpt-5-mini",
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
        reasoning_effort="high",
        response_format=ResponseFormat(
            type="json_schema",
            json_schema={"type": "object", "properties": {"answer": {"type": "string"}}},
            strict=True,
        ),
    )

    payload = adapter._build_payload(request)

    assert payload["instructions"] == "global safety\n\nteam style"
    assert payload["input"] == [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "first"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Working on it."}],
        },
        {
            "type": "function_call",
            "id": "call_1",
            "call_id": "call_1",
            "name": "get_weather",
            "arguments": '{"city": "SF"}',
        },
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "Sunny",
        },
    ]
    assert payload["tools"] == [
        {
            "type": "function",
            "name": "get_weather",
            "description": "Get weather by city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        }
    ]
    assert payload["tool_choice"] == {"type": "function", "name": "get_weather"}
    assert payload["reasoning"] == {"effort": "high"}
    assert payload["text"] == {
        "format": {
            "type": "json_schema",
            "schema": {"type": "object", "properties": {"answer": {"type": "string"}}},
            "strict": True,
        }
    }


def test_translate_tool_choice_modes():
    adapter = OpenAIAdapter(api_key="test-key")

    auto_payload = adapter._build_payload(
        Request(
            model="gpt-5-mini",
            messages=[Message.user("Hello")],
            tool_choice=ToolChoice(mode="auto"),
        )
    )
    none_payload = adapter._build_payload(
        Request(
            model="gpt-5-mini",
            messages=[Message.user("Hello")],
            tool_choice=ToolChoice(mode="none"),
        )
    )
    required_payload = adapter._build_payload(
        Request(
            model="gpt-5-mini",
            messages=[Message.user("Hello")],
            tool_choice=ToolChoice(mode="required"),
        )
    )

    assert auto_payload["tool_choice"] == "auto"
    assert none_payload["tool_choice"] == "none"
    assert required_payload["tool_choice"] == "required"
