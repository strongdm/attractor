"""Tests for core types: Role, ContentKind, ContentPart, Message."""

from attractor_llm.types import (
    AudioData,
    ContentKind,
    ContentPart,
    DocumentData,
    ImageData,
    Message,
    Role,
    ThinkingData,
    ToolCallData,
    ToolResultData,
)


class TestRole:
    def test_all_roles_exist(self):
        assert Role.SYSTEM
        assert Role.USER
        assert Role.ASSISTANT
        assert Role.TOOL
        assert Role.DEVELOPER

    def test_role_values_are_strings(self):
        assert Role.SYSTEM.value == "system"
        assert Role.USER.value == "user"
        assert Role.ASSISTANT.value == "assistant"
        assert Role.TOOL.value == "tool"
        assert Role.DEVELOPER.value == "developer"


class TestContentKind:
    def test_all_kinds_exist(self):
        assert ContentKind.TEXT
        assert ContentKind.IMAGE
        assert ContentKind.AUDIO
        assert ContentKind.DOCUMENT
        assert ContentKind.TOOL_CALL
        assert ContentKind.TOOL_RESULT
        assert ContentKind.THINKING
        assert ContentKind.REDACTED_THINKING


class TestImageData:
    def test_url_image(self):
        img = ImageData(url="https://example.com/img.png")
        assert img.url == "https://example.com/img.png"
        assert img.data is None
        assert img.media_type is None

    def test_base64_image(self):
        img = ImageData(data=b"fake-png-data", media_type="image/png")
        assert img.data == b"fake-png-data"
        assert img.media_type == "image/png"
        assert img.url is None

    def test_detail_hint(self):
        img = ImageData(url="https://example.com/img.png", detail="high")
        assert img.detail == "high"


class TestAudioData:
    def test_audio_url(self):
        audio = AudioData(url="https://example.com/audio.wav")
        assert audio.url == "https://example.com/audio.wav"

    def test_audio_data(self):
        audio = AudioData(data=b"raw-audio", media_type="audio/wav")
        assert audio.data == b"raw-audio"


class TestDocumentData:
    def test_document(self):
        doc = DocumentData(
            url="https://example.com/doc.pdf",
            media_type="application/pdf",
            file_name="report.pdf",
        )
        assert doc.url == "https://example.com/doc.pdf"
        assert doc.file_name == "report.pdf"


class TestToolCallData:
    def test_tool_call(self):
        tc = ToolCallData(
            id="call_123",
            name="get_weather",
            arguments={"location": "SF"},
        )
        assert tc.id == "call_123"
        assert tc.name == "get_weather"
        assert tc.arguments == {"location": "SF"}
        assert tc.type == "function"

    def test_tool_call_string_arguments(self):
        tc = ToolCallData(
            id="call_456",
            name="search",
            arguments='{"query": "hello"}',
        )
        assert tc.arguments == '{"query": "hello"}'


class TestToolResultData:
    def test_tool_result(self):
        tr = ToolResultData(
            tool_call_id="call_123",
            content="Sunny, 72F",
        )
        assert tr.tool_call_id == "call_123"
        assert tr.content == "Sunny, 72F"
        assert tr.is_error is False

    def test_tool_result_error(self):
        tr = ToolResultData(
            tool_call_id="call_123",
            content="Connection timeout",
            is_error=True,
        )
        assert tr.is_error is True

    def test_tool_result_with_image(self):
        tr = ToolResultData(
            tool_call_id="call_123",
            content="Chart generated",
            image_data=b"png-bytes",
            image_media_type="image/png",
        )
        assert tr.image_data == b"png-bytes"


class TestThinkingData:
    def test_thinking(self):
        t = ThinkingData(text="Let me think about this...")
        assert t.text == "Let me think about this..."
        assert t.signature is None
        assert t.redacted is False

    def test_redacted_thinking(self):
        t = ThinkingData(text="", redacted=True, signature="sig_abc")
        assert t.redacted is True
        assert t.signature == "sig_abc"


class TestContentPart:
    def test_text_part(self):
        part = ContentPart.text("Hello world")
        assert part.kind == ContentKind.TEXT
        assert part.text == "Hello world"

    def test_image_part(self):
        img = ImageData(url="https://example.com/img.png")
        part = ContentPart.image(img)
        assert part.kind == ContentKind.IMAGE
        assert part.image == img

    def test_tool_call_part(self):
        tc = ToolCallData(id="call_1", name="search", arguments={"q": "hi"})
        part = ContentPart.tool_call(tc)
        assert part.kind == ContentKind.TOOL_CALL
        assert part.tool_call == tc

    def test_tool_result_part(self):
        tr = ToolResultData(tool_call_id="call_1", content="result")
        part = ContentPart.tool_result(tr)
        assert part.kind == ContentKind.TOOL_RESULT
        assert part.tool_result == tr

    def test_thinking_part(self):
        td = ThinkingData(text="thinking...")
        part = ContentPart.thinking(td)
        assert part.kind == ContentKind.THINKING
        assert part.thinking == td

    def test_redacted_thinking_part(self):
        td = ThinkingData(text="", redacted=True)
        part = ContentPart.redacted_thinking(td)
        assert part.kind == ContentKind.REDACTED_THINKING
        assert part.thinking == td

    def test_audio_part(self):
        ad = AudioData(url="https://example.com/a.wav")
        part = ContentPart.audio(ad)
        assert part.kind == ContentKind.AUDIO
        assert part.audio == ad

    def test_document_part(self):
        dd = DocumentData(url="https://example.com/d.pdf")
        part = ContentPart.document(dd)
        assert part.kind == ContentKind.DOCUMENT
        assert part.document == dd


class TestMessage:
    def test_system_convenience(self):
        msg = Message.system("You are a helpful assistant.")
        assert msg.role == Role.SYSTEM
        assert len(msg.content) == 1
        assert msg.content[0].kind == ContentKind.TEXT
        assert msg.content[0].text == "You are a helpful assistant."

    def test_user_convenience(self):
        msg = Message.user("Hello!")
        assert msg.role == Role.USER
        assert msg.text == "Hello!"

    def test_assistant_convenience(self):
        msg = Message.assistant("Hi there!")
        assert msg.role == Role.ASSISTANT
        assert msg.text == "Hi there!"

    def test_tool_result_convenience(self):
        msg = Message.tool_result(
            tool_call_id="call_1",
            content="The weather is sunny",
        )
        assert msg.role == Role.TOOL
        assert msg.name is None
        assert msg.tool_call_id == "call_1"
        assert len(msg.content) == 1
        assert msg.content[0].kind == ContentKind.TOOL_RESULT

    def test_tool_result_error(self):
        msg = Message.tool_result(
            tool_call_id="call_1",
            content="Error: not found",
            is_error=True,
        )
        assert msg.content[0].tool_result.is_error is True

    def test_text_property_single_part(self):
        msg = Message.user("Hello world")
        assert msg.text == "Hello world"

    def test_text_property_multiple_parts(self):
        msg = Message(
            role=Role.ASSISTANT,
            content=[
                ContentPart.text("Part one. "),
                ContentPart.text("Part two."),
            ],
        )
        assert msg.text == "Part one. Part two."

    def test_text_property_mixed_parts(self):
        """Text property only concatenates text parts, ignoring others."""
        img = ImageData(url="https://example.com/img.png")
        msg = Message(
            role=Role.USER,
            content=[
                ContentPart.text("Look at this: "),
                ContentPart.image(img),
                ContentPart.text("What is it?"),
            ],
        )
        assert msg.text == "Look at this: What is it?"

    def test_text_property_no_text_parts(self):
        img = ImageData(url="https://example.com/img.png")
        msg = Message(
            role=Role.USER,
            content=[ContentPart.image(img)],
        )
        assert msg.text == ""

    def test_message_with_name(self):
        msg = Message(
            role=Role.TOOL,
            content=[ContentPart.text("result")],
            name="weather_tool",
        )
        assert msg.name == "weather_tool"

    def test_developer_message(self):
        msg = Message(
            role=Role.DEVELOPER,
            content=[ContentPart.text("System instruction")],
        )
        assert msg.role == Role.DEVELOPER
