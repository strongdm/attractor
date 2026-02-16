from attractor_agent.truncation import truncate_lines, truncate_output, truncate_tool_output


def test_truncate_output_head_tail_mode():
    text = "abcdefghij"
    out = truncate_output(text, max_chars=6, mode="head_tail")

    assert "abc" in out
    assert "hij" in out
    assert "truncated" in out


def test_truncate_output_tail_mode():
    text = "0123456789"
    out = truncate_output(text, max_chars=4, mode="tail")

    assert out.endswith("6789")
    assert "truncated" in out


def test_truncate_lines_keeps_head_and_tail():
    text = "\n".join(str(i) for i in range(1, 11))
    out = truncate_lines(text, max_lines=4)

    assert out.splitlines()[0] == "1"
    assert out.splitlines()[-1] == "10"
    assert "omitted" in out


def test_truncate_tool_output_applies_chars_then_lines():
    text = "x" * 80 + "\n" + "1\n2\n3\n4\n5\n6"
    out = truncate_tool_output(
        text,
        tool_name="shell",
        tool_char_limits={"shell": 40},
        tool_line_limits={"shell": 4},
    )

    assert len(out) <= 400
    assert "truncated" in out
    assert "omitted" in out
