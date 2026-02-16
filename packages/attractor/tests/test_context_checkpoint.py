from pathlib import Path

from attractor.checkpoint import Checkpoint, load_checkpoint, save_checkpoint
from attractor.context import Context


def test_context_mutation_is_consistent():
    context = Context({"count": 1})

    context.set("count", 2)
    context.update({"status": "ok"})

    assert context.get("count") == 2
    assert context.to_dict()["status"] == "ok"


def test_checkpoint_roundtrip(tmp_path: Path):
    checkpoint = Checkpoint(node_id="step", context={"a": 1}, history=["start", "step"])
    path = tmp_path / "state.json"

    save_checkpoint(path, checkpoint)
    loaded = load_checkpoint(path)

    assert loaded == checkpoint
