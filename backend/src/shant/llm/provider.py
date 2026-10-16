"""What the game needs from a language model. Providers implement this, so they can change."""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    text: str


class LLMRefusalError(Exception):
    """The model declined to answer, even after any fallback model."""


class LLM(Protocol):
    def stream(self, system: str, messages: Sequence[Message]) -> AsyncIterator[str]:
        """Yield the reply's text as it's generated."""
        ...


class StructuredLLM(Protocol):
    async def parse(self, system: str, messages: Sequence[Message], schema: type[T]) -> T:
        """Return the reply as a validated instance of `schema`."""
        ...
