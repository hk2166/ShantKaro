"""The state of one call. Plain frozen data; rules.py decides how it changes."""

from dataclasses import dataclass
from enum import StrEnum

from shant.tags import Tag


class Status(StrEnum):
    IN_PROGRESS = "in_progress"
    WON = "won"
    HUNG_UP = "hung_up"
    TIMED_OUT = "timed_out"
    ENDED_BY_TRAINEE = "ended_by_trainee"


@dataclass(frozen=True)
class Judgement:
    """The Judge's verdict on one trainee turn."""

    tags: frozenset[Tag]


@dataclass(frozen=True)
class Turn:
    """One applied judgement, kept for the report card."""

    tags: frozenset[Tag]
    anger_before: int
    anger_after: int


@dataclass(frozen=True)
class GameState:
    anger: int
    strikes: int = 0
    resolution_offered: bool = False
    language_switched: bool = False
    elapsed_s: float = 0.0
    status: Status = Status.IN_PROGRESS
    turns: tuple[Turn, ...] = ()

    @property
    def finished(self) -> bool:
        return self.status is not Status.IN_PROGRESS
