"""Core types: Role, ContentKind, ContentPart, Message and supporting data classes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Role(Enum):
    """Who produced a message."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    DEVELOPER = "developer"


class ContentKind(Enum):
    """Discriminator for ContentPart tagged union."""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    DOCUMENT = "document"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    THINKING = "thinking"
    REDACTED_THINKING = "redacted_thinking"


@dataclass(frozen=True)
class ImageData:
    """Image as URL, base64 data, or file reference."""

    url: str | None = None
    data: bytes | None = None
    media_type: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class AudioData:
    """Audio as URL or raw bytes."""

    url: str | None = None
    data: bytes | None = None
    media_type: str | None = None


@dataclass(frozen=True)
class DocumentData:
    """Document (PDF, etc.) as URL, base64, or file reference."""

    url: str | None = None
    data: bytes | None = None
    media_type: str | None = None
    file_name: str | None = None


@dataclass(frozen=True)
class ToolCallData:
    """A model-initiated tool invocation."""

    id: str
    name: str
    arguments: dict[str, Any] | str
    type: str = "function"


@dataclass(frozen=True)
class ToolResultData:
    """The result of executing a tool call."""

    tool_call_id: str
    content: str | dict[str, Any]
    is_error: bool = False
    image_data: bytes | None = None
    image_media_type: str | None = None


@dataclass(frozen=True)
class ThinkingData:
    """Model reasoning/thinking content."""

    text: str
    signature: str | None = None
    redacted: bool = False


@dataclass(frozen=True)
class ContentPart:
    """A single content part within a message. Tagged union via `kind` field."""

    kind: ContentKind
    text: str | None = None
    image: ImageData | None = None
    audio: AudioData | None = None
    document: DocumentData | None = None
    tool_call: ToolCallData | None = None
    tool_result: ToolResultData | None = None
    thinking: ThinkingData | None = None

    @staticmethod
    def text_part(text: str) -> ContentPart:
        """Create a text content part."""
        return ContentPart(kind=ContentKind.TEXT, text=text)

    # Alias for cleaner API - the static method name avoids shadowing the `text` field
    @classmethod
    def _text(cls, text: str) -> ContentPart:
        return cls.text_part(text)

    @staticmethod
    def image(image: ImageData) -> ContentPart:
        return ContentPart(kind=ContentKind.IMAGE, image=image)

    @staticmethod
    def audio(audio: AudioData) -> ContentPart:
        return ContentPart(kind=ContentKind.AUDIO, audio=audio)

    @staticmethod
    def document(document: DocumentData) -> ContentPart:
        return ContentPart(kind=ContentKind.DOCUMENT, document=document)

    @staticmethod
    def tool_call(tool_call: ToolCallData) -> ContentPart:
        return ContentPart(kind=ContentKind.TOOL_CALL, tool_call=tool_call)

    @staticmethod
    def tool_result(tool_result: ToolResultData) -> ContentPart:
        return ContentPart(kind=ContentKind.TOOL_RESULT, tool_result=tool_result)

    @staticmethod
    def thinking(thinking: ThinkingData) -> ContentPart:
        return ContentPart(kind=ContentKind.THINKING, thinking=thinking)

    @staticmethod
    def redacted_thinking(thinking: ThinkingData) -> ContentPart:
        return ContentPart(kind=ContentKind.REDACTED_THINKING, thinking=thinking)


# Make ContentPart.text() work as a constructor while keeping the text field
# We need a workaround since 'text' is both a field name and desired classmethod name
ContentPart.text = staticmethod(ContentPart.text_part)  # type: ignore[attr-defined]


@dataclass
class Message:
    """A single message in a conversation."""

    role: Role
    content: list[ContentPart] = field(default_factory=list)
    name: str | None = None
    tool_call_id: str | None = None

    @property
    def text(self) -> str:
        """Concatenate all TEXT content parts."""
        return "".join(
            part.text for part in self.content
            if part.kind == ContentKind.TEXT and part.text is not None
        )

    @classmethod
    def system(cls, text: str) -> Message:
        return cls(role=Role.SYSTEM, content=[ContentPart.text_part(text)])

    @classmethod
    def user(cls, text: str) -> Message:
        return cls(role=Role.USER, content=[ContentPart.text_part(text)])

    @classmethod
    def assistant(cls, text: str) -> Message:
        return cls(role=Role.ASSISTANT, content=[ContentPart.text_part(text)])

    @classmethod
    def tool_result(
        cls,
        tool_call_id: str,
        content: str,
        is_error: bool = False,
    ) -> Message:
        return cls(
            role=Role.TOOL,
            content=[
                ContentPart.tool_result(
                    ToolResultData(
                        tool_call_id=tool_call_id,
                        content=content,
                        is_error=is_error,
                    )
                )
            ],
            tool_call_id=tool_call_id,
        )
