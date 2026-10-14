import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import replace

from shant.agents.actor import Actor, system_prompt
from shant.engine.rules import start
from shant.llm.provider import Message
from shant.scenarios.loader import load_all

SCENARIOS = load_all()
SHARMA = SCENARIOS["sharma_uncle"]
LAKSHMI = SCENARIOS["lakshmi_aunty"]
OPENING = SHARMA.opening_lines[0]


def test_prompt_carries_the_scenarios_facts_and_policy() -> None:
    prompt = system_prompt(SHARMA, start(SHARMA), OPENING)
    for text in [*SHARMA.grievance.facts, *SHARMA.policy.allowed_remedies]:
        assert text in prompt
    for text in SHARMA.policy.forbidden_promises:
        assert text in prompt
    assert SHARMA.persona.speaking_style in prompt
    assert OPENING in prompt
    assert "$" not in prompt


def test_prompt_mood_follows_the_anger_band() -> None:
    calm = system_prompt(SHARMA, replace(start(SHARMA), anger=25), OPENING)
    furious = system_prompt(SHARMA, replace(start(SHARMA), anger=95), OPENING)
    assert SHARMA.voice.band_for(25).style in calm
    assert SHARMA.voice.band_for(95).style in furious
    assert "anger is 25 out of 100" in calm
    assert "anger is 95 out of 100" in furious


def test_prompt_mentions_the_language_switch_only_once_it_happens() -> None:
    before = system_prompt(LAKSHMI, start(LAKSHMI), LAKSHMI.opening_lines[0])
    after = system_prompt(
        LAKSHMI, replace(start(LAKSHMI), language_switched=True), LAKSHMI.opening_lines[0]
    )
    assert "speak only Tamil" not in before
    assert "speak only Tamil" in after


class FakeLLM:
    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks
        self.calls: list[tuple[str, list[Message]]] = []

    async def stream(self, system: str, messages: Sequence[Message]) -> AsyncIterator[str]:
        self.calls.append((system, list(messages)))
        for chunk in self.chunks:
            yield chunk


def test_reply_streams_the_llm_output_with_the_current_prompt() -> None:
    llm = FakeLLM(["तीन हफ्ते", " हो गए!"])
    actor = Actor(SHARMA, llm, OPENING)
    state = start(SHARMA)
    history = [Message("user", "sir refund process mein hai")]

    async def run() -> str:
        return "".join([chunk async for chunk in actor.reply(state, history)])

    assert asyncio.run(run()) == "तीन हफ्ते हो गए!"
    ((system, sent),) = llm.calls
    assert system == system_prompt(SHARMA, state, OPENING)
    assert sent == history
