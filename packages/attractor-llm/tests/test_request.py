"""Tests for Request, ToolDefinition, ToolChoice, ResponseFormat."""

from attractor_llm.request import Request, ResponseFormat, ToolChoice, ToolDefinition
from attractor_llm.types import Message


class TestToolDefinition:
    def test_basic_tool(self):
        tool = ToolDefinition(
            name="get_weather",
            description="Get current weather for a location",
            parameters={
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                },
                "required": ["location"],
            },
        )
        assert tool.name == "get_weather"
        assert tool.description == "Get current weather for a location"
        assert tool.parameters["type"] == "object"

    def test_tool_with_no_params(self):
        tool = ToolDefinition(
            name="get_time",
            description="Get current time",
            parameters={"type": "object", "properties": {}},
        )
        assert tool.parameters == {"type": "object", "properties": {}}


class TestToolChoice:
    def test_auto(self):
        tc = ToolChoice(mode="auto")
        assert tc.mode == "auto"
        assert tc.tool_name is None

    def test_none(self):
        tc = ToolChoice(mode="none")
        assert tc.mode == "none"

    def test_required(self):
        tc = ToolChoice(mode="required")
        assert tc.mode == "required"

    def test_named(self):
        tc = ToolChoice(mode="named", tool_name="get_weather")
        assert tc.mode == "named"
        assert tc.tool_name == "get_weather"


class TestResponseFormat:
    def test_text_format(self):
        rf = ResponseFormat(type="text")
        assert rf.type == "text"
        assert rf.json_schema is None
        assert rf.strict is False

    def test_json_format(self):
        rf = ResponseFormat(type="json")
        assert rf.type == "json"

    def test_json_schema_format(self):
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        rf = ResponseFormat(type="json_schema", json_schema=schema, strict=True)
        assert rf.type == "json_schema"
        assert rf.json_schema == schema
        assert rf.strict is True


class TestRequest:
    def test_minimal_request(self):
        req = Request(
            model="claude-opus-4-6",
            messages=[Message.user("Hello")],
        )
        assert req.model == "claude-opus-4-6"
        assert len(req.messages) == 1
        assert req.provider is None
        assert req.tools is None
        assert req.tool_choice is None
        assert req.temperature is None

    def test_full_request(self):
        tool = ToolDefinition(
            name="search",
            description="Search the web",
            parameters={"type": "object", "properties": {"q": {"type": "string"}}},
        )
        req = Request(
            model="gpt-5.2",
            messages=[Message.system("Be helpful"), Message.user("Search for cats")],
            provider="openai",
            tools=[tool],
            tool_choice=ToolChoice(mode="auto"),
            response_format=ResponseFormat(type="text"),
            temperature=0.7,
            top_p=0.9,
            max_tokens=1000,
            stop_sequences=["END"],
            reasoning_effort="high",
            metadata={"session": "abc"},
            provider_options={"openai": {"store": True}},
        )
        assert req.provider == "openai"
        assert len(req.tools) == 1
        assert req.temperature == 0.7
        assert req.reasoning_effort == "high"
        assert req.metadata == {"session": "abc"}
