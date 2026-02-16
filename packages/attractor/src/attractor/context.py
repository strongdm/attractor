from threading import RLock
from typing import Any


class Context:
    def __init__(self, initial: dict[str, Any] | None = None):
        self._lock = RLock()
        self._data: dict[str, Any] = dict(initial or {})

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def update(self, values: dict[str, Any]) -> None:
        with self._lock:
            self._data.update(values)

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)
