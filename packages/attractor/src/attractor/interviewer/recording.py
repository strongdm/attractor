class RecordingInterviewer:
    def __init__(self, wrapped):
        self._wrapped = wrapped
        self.history: list[tuple[str, str]] = []

    def ask(self, prompt: str) -> str:
        answer = self._wrapped.ask(prompt)
        self.history.append((prompt, answer))
        return answer
