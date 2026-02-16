from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StageStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    WAITING = "waiting"
    EXITED = "exited"


@dataclass(slots=True)
class Outcome:
    status: StageStatus
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    preferred_label: str | None = None
