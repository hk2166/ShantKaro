"""The report card: rubric scores, the best and worst line, and two coaching tips (task.md §4.2).

The scores are worked out from the Judge's tags and the engine's state, never by an LLM, so
the same call always gets the same score and nobody can talk their way to a better grade.
Only the coaching tips come from an LLM, and a tip may only quote words the trainee said.
"""

from dataclasses import astuple, dataclass
from pathlib import Path
from string import Template

from pydantic import BaseModel

from shant.agents.actor import bullets
from shant.agents.judge import normalise
from shant.engine.state import Status
from shant.game.call import Call, TurnRecord
from shant.llm.provider import Message, StructuredLLM
from shant.tags import AGGRAVATING, Tag

PROMPT = Template((Path(__file__).parent / "prompts" / "coach.md").read_text(encoding="utf-8"))
EMPATHY_TAGS = (Tag.ACKNOWLEDGED_FEELING, Tag.APOLOGISED, Tag.USED_NAME)
UNKIND_TAGS = {Tag.DISMISSIVE, Tag.BLAMED_CUSTOMER}
LONG_TURN_WORDS = 40  # about 15 seconds of speech: a monologue, not an answer
TIPS = 2


@dataclass(frozen=True)
class Scores:
    """Each dimension is out of 100. None means this call didn't test it."""

    empathy: int
    resolution: int
    policy_compliance: int
    language_adaptation: int | None
    efficiency: int

    @property
    def total(self) -> int:
        measured = [score for score in astuple(self) if score is not None]
        return round(sum(measured) / len(measured))


def tags_of(turn: TurnRecord) -> set[Tag]:
    return {evidence.tag for evidence in turn.verdict.tags}


def empathy(turns: list[TurnRecord]) -> int:
    """Variety (feeling, apology, name) times the share of turns that weren't unkind."""
    used = set().union(*(tags_of(turn) for turn in turns))
    variety = sum(tag in used for tag in EMPATHY_TAGS) / len(EMPATHY_TAGS)
    kind = sum(not tags_of(turn) & UNKIND_TAGS for turn in turns) / len(turns)
    return round(100 * variety * kind)


def resolution(call: Call) -> int:
    """An allowed next step earns 60; the customer accepting it (a win) earns the rest."""
    if call.state.status is Status.WON:
        return 100
    return 60 if call.state.resolution_offered else 0


def policy_compliance(call: Call) -> int:
    used = call.state.strikes / call.scenario.dynamics.max_strikes
    return max(0, round(100 * (1 - used)))


def language_adaptation(turns: list[TurnRecord]) -> int | None:
    """Share of the turns after the customer switched language where the agent followed."""
    after_switch = [turn for turn in turns if turn.language_switched]
    if not after_switch:
        return None
    followed = sum(Tag.FOLLOWED_LANGUAGE_SWITCH in tags_of(turn) for turn in after_switch)
    return round(100 * followed / len(after_switch))


def efficiency(call: Call) -> int:
    """How fast the customer was calmed, minus 10 for every monologue."""
    state, dynamics = call.state, call.scenario.dynamics
    if state.status is Status.WON:
        base = 100 - 50 * state.elapsed_s / dynamics.time_limit_s
    else:
        calmed = max(0, dynamics.starting_anger - state.anger)
        base = 50 * calmed / (dynamics.starting_anger - dynamics.win_at_or_below)
    monologues = sum(len(turn.agent.split()) > LONG_TURN_WORDS for turn in call.turns)
    return max(0, min(100, round(base - 10 * monologues)))


def score(call: Call) -> Scores:
    if not call.turns:
        raise ValueError("a call with no turns has nothing to score")
    return Scores(
        empathy=empathy(call.turns),
        resolution=resolution(call),
        policy_compliance=policy_compliance(call),
        language_adaptation=language_adaptation(call.turns),
        efficiency=efficiency(call),
    )


def impact(call: Call, turn: TurnRecord) -> int:
    """How much the turn's tags move this customer's anger, before clamping to 0–100."""
    weights = call.scenario.dynamics.tag_weights
    return sum(weights.get(tag, 0) for tag in tags_of(turn))


def best_line(call: Call) -> TurnRecord | None:
    """The most calming turn that did nothing wrong."""
    clean = [turn for turn in call.turns if not tags_of(turn) & AGGRAVATING]
    best = min(clean, key=lambda turn: impact(call, turn), default=None)
    return best if best is not None and impact(call, best) < 0 else None


def worst_line(call: Call) -> TurnRecord | None:
    """A forbidden promise first, then the turn that angered the customer most."""
    bad = [turn for turn in call.turns if tags_of(turn) & AGGRAVATING]
    return max(
        bad,
        key=lambda turn: (Tag.FORBIDDEN_PROMISE in tags_of(turn), impact(call, turn)),
        default=None,
    )


class Tip(BaseModel):
    quote: str
    advice: str
    try_saying: str


class Coaching(BaseModel):
    tips: list[Tip]


def system_prompt(call: Call) -> str:
    scenario = call.scenario
    return PROMPT.substitute(
        company=scenario.company.name,
        industry=scenario.company.industry,
        customer=scenario.persona.name,
        grievance=scenario.grievance.summary,
        remedies=bullets(scenario.policy.allowed_remedies),
        forbidden=bullets(scenario.policy.forbidden_promises),
    )


def call_summary(call: Call, scores: Scores) -> str:
    state, dynamics = call.state, call.scenario.dynamics
    lines = [
        f"Outcome: {state.status}, anger {state.anger}/100, "
        f"strikes {state.strikes}/{dynamics.max_strikes}",
        "Scores out of 100: "
        + ", ".join(
            f"{name.replace('_', ' ')} {value}"
            for name, value in vars(scores).items()
            if value is not None
        ),
        "",
        f"Customer: {call.actor.opening_line}",
    ]
    for turn in call.turns:
        tags = ", ".join(sorted(tags_of(turn))) or "none"
        lines += [f"Agent: {turn.agent}  [judge: {tags}]", f"Customer: {turn.customer}"]
    return "\n".join(lines)


async def coach(llm: StructuredLLM, call: Call, scores: Scores) -> list[Tip]:
    message = Message("user", call_summary(call, scores))
    coaching = await llm.parse(system_prompt(call), [message], Coaching)
    said = [normalise(turn.agent) for turn in call.turns]
    tips = [
        tip
        if any(normalise(tip.quote) in line for line in said)
        else tip.model_copy(update={"quote": ""})
        for tip in coaching.tips
    ]
    return tips[:TIPS]
