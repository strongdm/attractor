"""Tests for Gemini request translation."""

from attractor_llm.adapters.gemini import GeminiAdapter
from attractor_llm.request import Request, ResponseFormat, ToolChoice, ToolDefinition
from attractor_llm.types import ContentPart, Message, Role, ToolCallData


def test_translate_request_maps_messages_tools_and_generation_config():
    adapter = GeminiAdapter(api_key="test-key")
    request = Request(
        model="gemini-2.5-pro",
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
        max_tokens=123,
        response_format=ResponseFormat(
            type="json_schema",
            json_schema={"type": "object", "properties": {"answer": {"type": "string"}}},
            strict=True,
        ),
    )

    payload = adapter._build_payload(request)

    assert payload["systemInstruction"] == {
        "parts": [{"text": "global safety"}, {"text": "team style"}]
    }
    assert payload["contents"] == [
        {"role": "user", "parts": [{"text": "first"}]},
        {
            "role": "model",
            "parts": [
                {"text": "Working on it."},
                {
                    "functionCall": {
                        "id": "call_1",
                        "name": "get_weather",
                        "args": {"city": "SF"},
                    }
                },
            ],
        },
        {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": "get_weather",
                        "response": {"content": "Sunny"},
                    }
                }
            ],
        },
    ]
    assert payload["tools"] == [
        {
            "functionDeclarations": [
                {
                    "name": "get_weather",
                    "description": "Get weather by city",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                }
            ]
        }
    ]
    assert payload["toolConfig"] == {
        "functionCallingConfig": {
            "mode": "ANY",
            "allowedFunctionNames": ["get_weather"],
        }
    }
    assert payload["generationConfig"] == {
        "maxOutputTokens": 123,
        "responseMimeType": "application/json",
        "responseSchema": {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
        },
    }


def test_translate_tool_choice_none_and_required_modes():
    adapter = GeminiAdapter(api_key="test-key")

    none_payload = adapter._build_payload(
        Request(
            model="gemini-2.5-pro",
            messages=[Message.user("Hello")],
            tool_choice=ToolChoice(mode="none"),
        )
    )
    required_payload = adapter._build_payload(
        Request(
            model="gemini-2.5-pro",
            messages=[Message.user("Hello")],
            tool_choice=ToolChoice(mode="required"),
        )
    )

    assert none_payload["toolConfig"] == {"functionCallingConfig": {"mode": "NONE"}}
    assert required_payload["toolConfig"] == {"functionCallingConfig": {"mode": "ANY"}}


def test_translate_tool_result_uses_synthetic_call_id_mapping_when_missing():
    adapter = GeminiAdapter(api_key="test-key")
    request = Request(
        model="gemini-2.5-pro",
        messages=[
            Message(
                role=Role.ASSISTANT,
                content=[
                    ContentPart.tool_call(
                        ToolCallData(id="", name="search", arguments={"q": "mars"})
                    )
                ],
            ),
            Message.tool_result("", "ok"),
        ],
    )

    payload = adapter._build_payload(request)

    assert payload["contents"][0]["parts"][0]["functionCall"]["id"] == "call_1"
    assert payload["contents"][1]["parts"][0]["functionResponse"] == {
        "name": "search",
        "response": {"content": "ok"},
    }
