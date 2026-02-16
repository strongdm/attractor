from collections import deque


class QueueInterviewer:
    def __init__(self, responses: list[str] | None = None):
        self._responses = deque(responses or [])

    def push(self, response: str) -> None:
        self._responses.append(response)

    def ask(self, prompt: str) -> str:
        _ = prompt
        if not self._responses:
            return ""
        return self._responses.popleft()
