from collections.abc import Callable


class CallbackInterviewer:
    def __init__(self, callback: Callable[[str], str]):
        self._callback = callback

    def ask(self, prompt: str) -> str:
        return self._callback(prompt)
