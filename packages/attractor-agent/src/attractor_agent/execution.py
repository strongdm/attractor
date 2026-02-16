"""Execution environment abstraction and local implementation."""

from __future__ import annotations

import os
import platform
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExecResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    duration_ms: int


@dataclass(frozen=True)
class DirEntry:
    name: str
    is_dir: bool
    size: int | None


class LocalExecutionEnvironment:
    def __init__(self, working_dir: str | Path):
        self._working_dir = Path(working_dir).resolve()

    def initialize(self) -> None:
        return None

    def cleanup(self) -> None:
        return None

    def working_directory(self) -> str:
        return str(self._working_dir)

    def platform(self) -> str:
        return platform.system().lower()

    def os_version(self) -> str:
        return platform.platform()

    def resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return (self._working_dir / candidate).resolve()

    def read_text(self, path: str) -> str:
        return self.resolve_path(path).read_text(encoding="utf-8")

    def write_text(self, path: str, content: str) -> int:
        target = self.resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return len(content.encode("utf-8"))

    def read_file(self, path: str, offset: int | None = None, limit: int | None = None) -> str:
        raw = self.read_text(path).splitlines()
        start_idx = max((offset or 1) - 1, 0)
        if limit is None:
            selected = raw[start_idx:]
        else:
            selected = raw[start_idx : start_idx + limit]
        numbered = [f"{start_idx + idx + 1}: {line}" for idx, line in enumerate(selected)]
        return "\n".join(numbered)

    def write_file(self, path: str, content: str) -> int:
        return self.write_text(path, content)

    def file_exists(self, path: str) -> bool:
        return self.resolve_path(path).exists()

    def list_directory(self, path: str) -> list[DirEntry]:
        root = self.resolve_path(path)
        entries = []
        for child in sorted(root.iterdir(), key=lambda item: item.name):
            size = None if child.is_dir() else child.stat().st_size
            entries.append(DirEntry(name=child.name, is_dir=child.is_dir(), size=size))
        return entries

    def exec_command(
        self,
        command: str,
        timeout_ms: int,
        working_dir: str | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> ExecResult:
        cwd = self.resolve_path(working_dir) if working_dir else self._working_dir
        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)

        start = time.time()
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            text=True,
        )

        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout_ms / 1000)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            stdout, stderr = process.communicate()

        duration_ms = int((time.time() - start) * 1000)
        return ExecResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=process.returncode,
            timed_out=timed_out,
            duration_ms=duration_ms,
        )

    def grep(
        self,
        pattern: str,
        path: str = ".",
        glob_filter: str | None = None,
        case_insensitive: bool = False,
        max_results: int = 100,
    ) -> str:
        base = self.resolve_path(path)
        targets: list[Path]
        if base.is_file():
            targets = [base]
        else:
            if glob_filter:
                targets = [p for p in base.rglob(glob_filter) if p.is_file()]
            else:
                targets = [p for p in base.rglob("*") if p.is_file()]

        flags = re.IGNORECASE if case_insensitive else 0
        regex = re.compile(pattern, flags)
        matches: list[str] = []
        for file_path in targets:
            try:
                lines = file_path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            rel = file_path.relative_to(self._working_dir)
            for idx, line in enumerate(lines, start=1):
                if regex.search(line):
                    matches.append(f"{rel}:{idx}:{line}")
                    if len(matches) >= max_results:
                        return "\n".join(matches)
        return "\n".join(matches)

    def glob(self, pattern: str, path: str = ".") -> list[str]:
        base = self.resolve_path(path)
        paths = [p for p in base.glob(pattern)]
        paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return [str(p.relative_to(self._working_dir)) for p in paths]
