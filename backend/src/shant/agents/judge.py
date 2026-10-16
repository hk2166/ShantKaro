"""The Judge: labels each trainee line with behaviour tags, each backed by a quote."""

from pathlib import Path
from string import Template

from pydantic import BaseModel

from shant.agents.actor import LANGUAGE_NAMES, bullets
from shant.engine.state import Judgement
from shant.llm.provider import Message, StructuredLLM
from shant.scenarios.schema import Scenario
from shant.tags import Tag

PROMPT = Template((Path(__file__).parent / "prompts" / "judge.md").read_text(encoding="utf-8"))


class TagEvidence(BaseModel):
    tag: Tag
    quote: str


def normalise(text: str) -> str:
    """Lowercase and collapse whitespace, so we can check if a quote is in a line."""
    return " ".join(text.lower().split())


class Verdict(BaseModel):
    tags: list[TagEvidence]

    def grounded_in(self, agent_line: str) -> "Verdict":
        """Drop tags whose quote doesn't actually appear in the agent's line."""
        line = normalise(agent_line)
        kept = [
            evidence
            for evidence in self.tags
            if (quote := normalise(evidence.quote)) and quote in line
        ]
        return Verdict(tags=kept)

    def judgement(self) -> Judgement:
        return Judgement(frozenset(evidence.tag for evidence in self.tags))


def system_prompt(scenario: Scenario, language_switched: bool) -> str:
    switch = scenario.dynamics.language_switch
    if language_switched and switch is not None:
        language = LANGUAGE_NAMES.get(switch.language, switch.language)
        language_note = f"The customer has switched to speaking {language}."
    else:
        language_note = (
            "The customer has not switched language, so followed_language_switch can't apply."
        )
    return PROMPT.substitute(
        company=scenario.company.name,
        industry=scenario.company.industry,
        remedies=bullets(scenario.policy.allowed_remedies),
        forbidden=bullets(scenario.policy.forbidden_promises),
        language_note=language_note,
    )


async def judge(
    llm: StructuredLLM,
    scenario: Scenario,
    customer_line: str,
    agent_line: str,
    language_switched: bool,
) -> Verdict:
    message = Message(
        "user", f"Customer's last line: {customer_line}\nAgent's line to judge: {agent_line}"
    )
    verdict = await llm.parse(system_prompt(scenario, language_switched), [message], Verdict)
    return verdict.grounded_in(agent_line)
