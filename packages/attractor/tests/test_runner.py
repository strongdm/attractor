from pathlib import Path

from attractor.runner import run


def test_runner_composes_parse_validate_execute(tmp_path: Path):
    dot = """
    digraph Flow {
      start [type=start, handler=start];
      finish [type=exit, handler=exit];
      start -> finish;
    }
    """

    result = run(dot_source=dot, artifact_dir=tmp_path)

    assert result.outcome.status.value == "exited"
    assert result.visited_nodes == ["start", "finish"]
