"""Fake LLMs that play back scripted replies, so game tests need no network."""

from collections.abc import AsyncIterator, Sequence

from shant.agents.judge import Verdict
from shant.agents.reporter import Coaching, Tip
from shant.llm.provider import LLMRefusalError, Message, T


class ScriptedActor:
    """Plays back customer lines in order, and remembers the state it was shown."""

    def __init__(self, lines: list[str], fail: bool = False) -> None:
        self.lines = list(lines)
        self.fail = fail
        self.systems: list[str] = []

    async def stream(self, system: str, messages: Sequence[Message]) -> AsyncIterator[str]:
        self.systems.append(system)
        if self.fail:
            raise LLMRefusalError("declined")
        for word in self.lines.pop(0).split(" "):
            yield word + " "


class ScriptedJudge:
    def __init__(self, verdicts: list[Verdict]) -> None:
        self.verdicts = list(verdicts)
        self.calls: list[list[Message]] = []

    async def parse(self, system: str, messages: Sequence[Message], schema: type[T]) -> T:
        self.calls.append(list(messages))
        return schema.model_validate(self.verdicts.pop(0).model_dump())


class ScriptedCoach:
    """Returns the given tips, or refuses like a model that declined to answer."""

    def __init__(self, tips: list[Tip], fail: bool = False) -> None:
        self.tips = tips
        self.fail = fail

    async def parse(self, system: str, messages: Sequence[Message], schema: type[T]) -> T:
        if self.fail:
            raise LLMRefusalError("declined")
        return schema.model_validate(Coaching(tips=self.tips).model_dump())
