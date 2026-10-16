"""One training call: the customer, the Judge and the engine working together.

Each turn follows task.md §5.1: the customer replies straight away from the current state,
while the Judge labels the agent's line in parallel. The Judge's verdict then moves the
engine, so the customer's mood follows one turn behind, and the reply is never slowed down.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from shant.agents.actor import Actor
from shant.agents.judge import Verdict, judge
from shant.engine.rules import apply, end_by_trainee, start, tick
from shant.engine.state import GameState
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
    ) -> TurnRecord:
        """Run one turn. `on_text` receives the customer's reply as it streams."""
        if self.state.finished:
            raise CallOverError(f"the call already ended: {self.state.status}")
        customer_before = self.last_customer_line
        self.history.append(Message("user", agent_line))
        verdict_task = asyncio.create_task(
            judge(
                self._judge_llm,
                self.scenario,
                customer_before,
                agent_line,
                self.state.language_switched,
            )
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
        customer = for_speech("".join(chunks))
        self.history.append(Message("assistant", customer))

        verdict = await verdict_task
        anger_before = self.state.anger
        self.state = apply(self.state, verdict.judgement(), self.scenario, elapsed_s)
        record = TurnRecord(
            agent_line, customer, verdict, anger_before, self.state.anger, elapsed_s
        )
        self.turns.append(record)
        return record

    def tick(self, elapsed_s: float) -> None:
        self.state = tick(self.state, self.scenario, elapsed_s)

    def hang_up(self) -> None:
        self.state = end_by_trainee(self.state)

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
                }
                for turn in self.turns
            ],
        }
