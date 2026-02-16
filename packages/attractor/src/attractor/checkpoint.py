import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Checkpoint:
    node_id: str
    context: dict[str, Any] = field(default_factory=dict)
    history: list[str] = field(default_factory=list)


def save_checkpoint(path: str | Path, checkpoint: Checkpoint) -> None:
    output_path = Path(path)
    output_path.write_text(json.dumps(asdict(checkpoint), indent=2), encoding="utf-8")


def load_checkpoint(path: str | Path) -> Checkpoint:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return Checkpoint(
        node_id=payload["node_id"],
        context=dict(payload.get("context", {})),
        history=list(payload.get("history", [])),
    )
