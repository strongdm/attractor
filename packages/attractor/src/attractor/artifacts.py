from pathlib import Path


class ArtifactStore:
    def __init__(self, base_path: str | Path):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def write_text(self, name: str, content: str) -> Path:
        path = self.base_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path
