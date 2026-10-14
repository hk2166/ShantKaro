"""The customer: an LLM playing the scenario's persona, steered by the engine's state."""

from collections.abc import AsyncIterator, Iterable, Sequence
from pathlib import Path
from string import Template

from shant.engine.state import GameState
from shant.llm.provider import LLM, Message
from shant.scenarios.schema import Scenario

PROMPT = Template((Path(__file__).parent / "prompts" / "actor.md").read_text(encoding="utf-8"))
LANGUAGE_NAMES = {
    "bn-IN": "Bengali",
    "en-IN": "English",
    "gu-IN": "Gujarati",
    "hi-IN": "Hindi",
    "kn-IN": "Kannada",
    "ml-IN": "Malayalam",
    "mr-IN": "Marathi",
    "pa-IN": "Punjabi",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
}


def bullets(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def system_prompt(scenario: Scenario, state: GameState, opening_line: str) -> str:
    persona = scenario.persona
    switch = scenario.dynamics.language_switch
    language_note = ""
    if state.language_switched and switch is not None:
        language = LANGUAGE_NAMES.get(switch.language, switch.language)
        language_note = f"\nYou are now so upset that you speak only {language}."
    return PROMPT.substitute(
        name=persona.name,
        age=persona.age,
        city=persona.city,
        company=scenario.company.name,
        industry=scenario.company.industry,
        background=persona.background,
        facts=bullets(scenario.grievance.facts),
        speaking_style=persona.speaking_style,
        remedies=bullets(scenario.policy.allowed_remedies),
        too_good=bullets(scenario.policy.forbidden_promises),
        opening_line=opening_line,
        anger=state.anger,
        mood=scenario.voice.band_for(state.anger).style,
        language_note=language_note,
    )


class Actor:
    def __init__(self, scenario: Scenario, llm: LLM, opening_line: str) -> None:
        self.scenario = scenario
        self.opening_line = opening_line
        self._llm = llm

    async def reply(self, state: GameState, history: Sequence[Message]) -> AsyncIterator[str]:
        """Stream the customer's next line. `history` must end with the agent's turn."""
        prompt = system_prompt(self.scenario, state, self.opening_line)
        async for chunk in self._llm.stream(prompt, history):
            yield chunk
