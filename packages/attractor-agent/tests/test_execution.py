from pathlib import Path

from attractor_agent.execution import LocalExecutionEnvironment


def test_local_execution_environment_file_and_search_methods(tmp_path: Path):
    env = LocalExecutionEnvironment(tmp_path)
    env.write_file("a.txt", "hello\nworld\n")
    env.write_file("b.py", "print('ok')\n")

    assert env.file_exists("a.txt")
    assert "1: hello" in env.read_file("a.txt", offset=1, limit=2)

    entries = env.list_directory(".")
    names = {e.name for e in entries}
    assert "a.txt" in names
    assert "b.py" in names

    grep = env.grep("hello", ".")
    assert "a.txt" in grep

    matches = env.glob("**/*.py", ".")
    assert any(path.endswith("b.py") for path in matches)


def test_local_execution_environment_exec_success_and_timeout(tmp_path: Path):
    env = LocalExecutionEnvironment(tmp_path)

    ok = env.exec_command("python -c \"print('ok')\"", timeout_ms=5000)
    assert ok.exit_code == 0
    assert "ok" in ok.stdout
    assert not ok.timed_out

    timeout = env.exec_command('python -c "import time; time.sleep(1)"', timeout_ms=50)
    assert timeout.timed_out
