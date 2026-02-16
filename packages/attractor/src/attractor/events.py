from dataclasses import dataclass

from attractor.outcome import Outcome


@dataclass(slots=True)
class NodeStarted:
    node_id: str


@dataclass(slots=True)
class NodeCompleted:
    node_id: str
    outcome: Outcome
