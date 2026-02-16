from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Token:
    kind: str
    value: str
    position: int


SINGLE_CHAR_TOKENS = {
    "{": "LBRACE",
    "}": "RBRACE",
    "[": "LBRACKET",
    "]": "RBRACKET",
    "=": "EQUALS",
    ",": "COMMA",
    ";": "SEMICOLON",
}


def lex(source: str) -> list[Token]:
    tokens: list[Token] = []
    index = 0
    length = len(source)

    while index < length:
        char = source[index]
        if char.isspace():
            index += 1
            continue

        if source.startswith("//", index):
            index = _skip_to_line_end(source, index)
            continue

        if char == '"':
            value, index = _read_string(source, index)
            tokens.append(Token("STRING", value, index))
            continue

        if source.startswith("->", index):
            tokens.append(Token("ARROW", "->", index))
            index += 2
            continue

        token_kind = SINGLE_CHAR_TOKENS.get(char)
        if token_kind is not None:
            tokens.append(Token(token_kind, char, index))
            index += 1
            continue

        if _is_identifier_start(char):
            value, index = _read_identifier(source, index)
            tokens.append(Token("IDENT", value, index))
            continue

        raise ValueError(f"Unexpected character {char!r} at index {index}")

    tokens.append(Token("EOF", "", len(source)))
    return tokens


def _skip_to_line_end(source: str, index: int) -> int:
    while index < len(source) and source[index] != "\n":
        index += 1
    return index


def _read_string(source: str, index: int) -> tuple[str, int]:
    index += 1
    result: list[str] = []

    while index < len(source):
        char = source[index]
        if char == '"':
            return "".join(result), index + 1
        if char == "\\" and index + 1 < len(source):
            index += 1
            result.append(source[index])
        else:
            result.append(char)
        index += 1

    raise ValueError("Unterminated string literal")


def _read_identifier(source: str, index: int) -> tuple[str, int]:
    start = index
    while index < len(source) and _is_identifier_part(source[index]):
        index += 1
    return source[start:index], index


def _is_identifier_start(char: str) -> bool:
    return char.isalnum() or char in "_.#-"


def _is_identifier_part(char: str) -> bool:
    return char.isalnum() or char in "_.#-"
