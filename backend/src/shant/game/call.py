"""One training call: the customer, the Judge and the engine working together.

Each turn follows task.md §5.1: the customer replies straight away from the current state,
while the Judge labels the agent's line in parallel. The Judge's verdict then moves the
engine, so the customer's mood follows one turn behind, and the reply is never slowed down.
"""

import asyncio
import random
from collections.abc import Callable
from dataclasses import dataclass

from shant.agents.actor import Actor
from shant.agents.judge import Verdict, judge
from shant.engine.rules import apply, end_by_trainee, start, tick
from shant.engine.state import GameState, Status
from shant.llm.provider import LLM, Message, StructuredLLM
from shant.scenarios.schema import Scenario
from shant.voice.formatter import for_speech


class CallOverError(Exception):
    """The call has already ended, so it can't take another turn."""


@dataclass(frozen=True)
class TurnRecord:
    agent: str
    customer: str
    verdict: Verdict
    anger_before: int
    anger_after: int
    elapsed_s: float
    language_switched: bool


class Call:
    def __init__(
        self, scenario: Scenario, actor_llm: LLM, judge_llm: StructuredLLM, opening_line: str
    ) -> None:
        self.scenario = scenario
        self.actor = Actor(scenario, actor_llm, opening_line)
        self.state: GameState = start(scenario)
        self.history: list[Message] = []
        self.turns: list[TurnRecord] = []
        self._judge_llm = judge_llm

    @property
    def last_customer_line(self) -> str:
        replies = [m.text for m in self.history if m.role == "assistant"]
        return replies[-1] if replies else self.actor.opening_line

    async def respond(
        self,
        agent_line: str,
        elapsed_s: float,
        on_text: Callable[[str], None] = lambda _: None,
        on_reply_done: Callable[[], None] = lambda: None,
    ) -> TurnRecord:
        """Run one turn. `on_text` receives the customer's reply as it streams.

        `on_reply_done` is called as soon as the reply has finished streaming, before waiting
        for the Judge, so a voice can finish speaking without that wait.
        """

        if self.state.finished:
            raise CallOverError(f"the call already ended: {self.state.status}")
        customer_before = self.last_customer_line
        switched = self.state.language_switched
        self.history.append(Message("user", agent_line))
        verdict_task = asyncio.create_task(
            judge(self._judge_llm, self.scenario, customer_before, agent_line, switched)
        )

        chunks: list[str] = []
        try:
            async for chunk in self.actor.reply(self.state, self.history):
                chunks.append(chunk)
                on_text(chunk)
        except BaseException:
            verdict_task.cancel()
            self.history.pop()
            raise
        on_reply_done()
        customer = for_speech("".join(chunks))
        self.history.append(Message("assistant", customer))

        verdict = await verdict_task
        anger_before = self.state.anger
        self.state = apply(self.state, verdict.judgement(), self.scenario, elapsed_s)
        record = TurnRecord(
            agent_line, customer, verdict, anger_before, self.state.anger, elapsed_s, switched
        )
        self.turns.append(record)
        return record

    def tick(self, elapsed_s: float) -> None:
        self.state = tick(self.state, self.scenario, elapsed_s)

    def hang_up(self) -> None:
        self.state = end_by_trainee(self.state)

    def closing_line(self) -> str | None:
        """What the customer says as the call ends, or None if they don't get a last word."""
        endings = self.scenario.closing_lines
        lines = {
            Status.WON: endings.won,
            Status.HUNG_UP: endings.hung_up,
            Status.TIMED_OUT: endings.timed_out,
        }.get(self.state.status)
        return random.choice(lines) if lines else None

    def snapshot(self) -> dict:
        """What the trainee's screen shows: sent to the browser whenever it changes."""
        state, dynamics = self.state, self.scenario.dynamics
        last = self.turns[-1].verdict.tags if self.turns else []
        return {
            "anger": state.anger,
            "strikes": state.strikes,
            "max_strikes": dynamics.max_strikes,
            "elapsed_s": round(state.elapsed_s),
            "time_limit_s": dynamics.time_limit_s,
            "status": str(state.status),
            "last_tags": [str(evidence.tag) for evidence in last],
        }

    def transcript(self) -> dict:
        return {
            "scenario": self.scenario.id,
            "opening_line": self.actor.opening_line,
            "status": str(self.state.status),
            "final_anger": self.state.anger,
            "strikes": self.state.strikes,
            "turns": [
                {
                    "agent": turn.agent,
                    "customer": turn.customer,
                    "tags": turn.verdict.model_dump()["tags"],
                    "anger_before": turn.anger_before,
                    "anger_after": turn.anger_after,
                    "elapsed_s": turn.elapsed_s,
                    "language_switched": turn.language_switched,
                }
                for turn in self.turns
            ],
        }
