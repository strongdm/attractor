import pytest

from attractor_agent.execution import LocalExecutionEnvironment
from attractor_agent.tools.apply_patch import apply_patch_tool
from attractor_agent.tools.edit_file import edit_file_tool
from attractor_agent.tools.glob import glob_tool
from attractor_agent.tools.grep import grep_tool
from attractor_agent.tools.read_file import read_file_tool
from attractor_agent.tools.registry import ToolRegistry
from attractor_agent.tools.shell import shell_tool
from attractor_agent.tools.write_file import write_file_tool


async def test_tool_registry_executes_registered_tool(tmp_path):
    env = LocalExecutionEnvironment(tmp_path)
    registry = ToolRegistry()
    registry.register(write_file_tool())

    out = await registry.execute("write_file", {"file_path": "x.txt", "content": "data"}, env)
    assert "written" in out.lower()
    assert (tmp_path / "x.txt").read_text() == "data"


async def test_file_tools_round_trip(tmp_path):
    env = LocalExecutionEnvironment(tmp_path)
    registry = ToolRegistry()
    registry.register(write_file_tool())
    registry.register(read_file_tool())
    registry.register(edit_file_tool())

    await registry.execute("write_file", {"file_path": "x.txt", "content": "one\ntwo\n"}, env)
    read = await registry.execute("read_file", {"file_path": "x.txt"}, env)
    assert "1: one" in read

    edited = await registry.execute(
        "edit_file",
        {"file_path": "x.txt", "old_string": "two", "new_string": "three"},
        env,
    )
    assert "1 replacement" in edited
    assert (tmp_path / "x.txt").read_text() == "one\nthree\n"


async def test_shell_grep_glob_tools(tmp_path):
    env = LocalExecutionEnvironment(tmp_path)
    registry = ToolRegistry()
    registry.register(shell_tool())
    registry.register(grep_tool())
    registry.register(glob_tool())
    registry.register(write_file_tool())

    await registry.execute("write_file", {"file_path": "a.py", "content": "print('x')\n"}, env)
    shell_out = await registry.execute(
        "shell", {"command": "python -c \"print('ok')\"", "timeout_ms": 1000}, env
    )
    grep_out = await registry.execute("grep", {"pattern": "print", "path": "."}, env)
    glob_out = await registry.execute("glob", {"pattern": "**/*.py", "path": "."}, env)

    assert "ok" in shell_out
    assert "a.py" in grep_out
    assert "a.py" in glob_out


async def test_apply_patch_add_update_delete(tmp_path):
    env = LocalExecutionEnvironment(tmp_path)
    registry = ToolRegistry()
    registry.register(apply_patch_tool())

    add_patch = """*** Begin Patch
*** Add File: hello.txt
+hello
*** End Patch
"""
    out1 = await registry.execute("apply_patch", {"patch": add_patch}, env)
    assert "hello.txt" in out1
    assert (tmp_path / "hello.txt").read_text() == "hello\n"

    update_patch = """*** Begin Patch
*** Update File: hello.txt
@@
-hello
+hi
*** End Patch
"""
    await registry.execute("apply_patch", {"patch": update_patch}, env)
    assert (tmp_path / "hello.txt").read_text() == "hi\n"

    delete_patch = """*** Begin Patch
*** Delete File: hello.txt
*** End Patch
"""
    out3 = await registry.execute("apply_patch", {"patch": delete_patch}, env)
    assert "deleted" in out3.lower()
    assert not (tmp_path / "hello.txt").exists()


async def test_edit_file_errors_on_ambiguous_match(tmp_path):
    env = LocalExecutionEnvironment(tmp_path)
    registry = ToolRegistry()
    registry.register(write_file_tool())
    registry.register(edit_file_tool())

    await registry.execute("write_file", {"file_path": "x.txt", "content": "a\na\n"}, env)
    with pytest.raises(ValueError, match="multiple"):
        await registry.execute(
            "edit_file",
            {"file_path": "x.txt", "old_string": "a", "new_string": "b"},
            env,
        )
