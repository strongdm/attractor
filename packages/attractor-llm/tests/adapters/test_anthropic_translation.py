"""Tests for Anthropic request translation."""

from attractor_llm.adapters.anthropic import AnthropicAdapter
from attractor_llm.request import Request, ToolChoice, ToolDefinition
from attractor_llm.types import ContentPart, Message, Role, ToolCallData


def test_translate_request_extracts_system_and_merges_roles():
    adapter = AnthropicAdapter(api_key="test-key")
    request = Request(
        model="claude-sonnet-4-5-20250929",
        messages=[
            Message.system("global safety"),
            Message(role=Role.DEVELOPER, content=[ContentPart.text("team style")]),
            Message.user("first"),
            Message.user("second"),
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
        tool_choice=ToolChoice(mode="auto"),
    )

    payload = adapter._build_payload(request)

    assert payload["max_tokens"] == 4096
    assert payload["system"] == [
        {"type": "text", "text": "global safety"},
        {"type": "text", "text": "team style"},
    ]

    assert [message["role"] for message in payload["messages"]] == ["user", "assistant", "user"]
    assert payload["messages"][0]["content"] == [
        {"type": "text", "text": "first"},
        {"type": "text", "text": "second"},
    ]
    assert payload["messages"][1]["content"][1] == {
        "type": "tool_use",
        "id": "call_1",
        "name": "get_weather",
        "input": {"city": "SF"},
    }
    assert payload["messages"][2]["content"] == [
        {
            "type": "tool_result",
            "tool_use_id": "call_1",
            "content": "Sunny",
            "is_error": False,
        }
    ]

    assert payload["tools"] == [
        {
            "name": "get_weather",
            "description": "Get weather by city",
            "input_schema": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        }
    ]
    assert payload["tool_choice"] == {"type": "auto"}


def test_translate_tool_choice_none_omits_tools():
    adapter = AnthropicAdapter(api_key="test-key")
    request = Request(
        model="claude-sonnet-4-5-20250929",
        messages=[Message.user("Hello")],
        tools=[
            ToolDefinition(
                name="noop",
                description="No-op",
                parameters={"type": "object", "properties": {}},
            )
        ],
        tool_choice=ToolChoice(mode="none"),
    )

    payload = adapter._build_payload(request)

    assert "tools" not in payload
    assert "tool_choice" not in payload


def test_headers_include_anthropic_beta_from_provider_options():
    adapter = AnthropicAdapter(api_key="test-key")
    request = Request(
        model="claude-sonnet-4-5-20250929",
        messages=[Message.user("Hello")],
        provider_options={"anthropic": {"beta_headers": ["beta-a", "beta-b"]}},
    )

    headers = adapter._build_headers(request)

    assert headers["x-api-key"] == "test-key"
    assert headers["anthropic-version"] == "2023-06-01"
    assert headers["anthropic-beta"] == "beta-a,beta-b"


def test_translate_tool_choice_required_and_named():
    adapter = AnthropicAdapter(api_key="test-key")

    required_payload = adapter._build_payload(
        Request(
            model="claude-sonnet-4-5-20250929",
            messages=[Message.user("go")],
            tools=[
                ToolDefinition(
                    name="search",
                    description="Search",
                    parameters={"type": "object", "properties": {}},
                )
            ],
            tool_choice=ToolChoice(mode="required"),
        )
    )
    named_payload = adapter._build_payload(
        Request(
            model="claude-sonnet-4-5-20250929",
            messages=[Message.user("go")],
            tools=[
                ToolDefinition(
                    name="search",
                    description="Search",
                    parameters={"type": "object", "properties": {}},
                )
            ],
            tool_choice=ToolChoice(mode="named", tool_name="search"),
        )
    )

    assert required_payload["tool_choice"] == {"type": "any"}
    assert named_payload["tool_choice"] == {"type": "tool", "name": "search"}
