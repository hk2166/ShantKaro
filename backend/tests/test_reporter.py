import asyncio

import pytest
from fakes import ScriptedActor, ScriptedCoach, ScriptedJudge

from shant.agents.judge import TagEvidence, Verdict
from shant.agents.reporter import (
    Scores,
    Tip,
    best_line,
    call_summary,
    coach,
    score,
    system_prompt,
    worst_line,
)
from shant.engine.state import Status
from shant.game.call import Call
from shant.scenarios.loader import load_all
from shant.scenarios.schema import Scenario
from shant.tags import Tag

SCENARIOS = load_all()
SHARMA = SCENARIOS["sharma_uncle"]
LAKSHMI = SCENARIOS["lakshmi_aunty"]
ROHAN = SCENARIOS["rohan"]

# Sharma Uncle starts at anger 75 and is won at 20 or below with a fix on the table.
GOOD_CALL = (
    (
        "sharma ji i am really sorry teen hafte bahut lamba hai",
        {Tag.USED_NAME, Tag.APOLOGISED, Tag.ACKNOWLEDGED_FEELING},
    ),
    (
        "i understand how frustrating this is sorry again",
        {Tag.ACKNOWLEDGED_FEELING, Tag.APOLOGISED},
    ),
    ("sharma ji ticket bkr4562 raised refund in 48 hours", {Tag.USED_NAME, Tag.CONCRETE_NEXT_STEP}),
)


def played(scenario: Scenario, *turns: tuple[str, set[Tag]], seconds_per_turn: float = 20) -> Call:
    """Play a call where each turn is the agent's line and the tags the Judge gives it."""
    verdicts = [
        Verdict(tags=[TagEvidence(tag=tag, quote=line) for tag in tags]) for line, tags in turns
    ]
    call = Call(
        scenario, ScriptedActor(["theek hai"] * len(turns)), ScriptedJudge(verdicts), "hello?"
    )

    async def play_all() -> None:
        for number, (line, _) in enumerate(turns, start=1):
            await call.respond(line, number * seconds_per_turn)

    asyncio.run(play_all())
    return call


def test_a_good_call_scores_full_marks_except_for_time() -> None:
    call = played(SHARMA, *GOOD_CALL)
    assert call.state.status is Status.WON
    assert score(call) == Scores(
        empathy=100,
        resolution=100,
        policy_compliance=100,
        language_adaptation=None,
        efficiency=83,  # won at 1:00 of 3:00
    )


def test_unkind_turns_cut_empathy() -> None:
    call = played(
        SHARMA,
        ("sharma ji sorry i understand", {Tag.USED_NAME, Tag.APOLOGISED, Tag.ACKNOWLEDGED_FEELING}),
        ("these things happen", {Tag.DISMISSIVE}),
    )
    assert score(call).empathy == 50


def test_resolution_needs_a_fix_and_full_marks_need_the_customer_to_accept_it() -> None:
    assert score(played(SHARMA, ("sorry", {Tag.APOLOGISED}))).resolution == 0
    assert score(played(SHARMA, ("ticket raised", {Tag.CONCRETE_NEXT_STEP}))).resolution == 60
    assert score(played(SHARMA, *GOOD_CALL)).resolution == 100


def test_each_strike_costs_its_share_of_the_policy_score() -> None:
    call = played(ROHAN, ("i will reverse it right now", {Tag.FORBIDDEN_PROMISE}))
    assert score(call).policy_compliance == 50  # Rohan allows 2 strikes


def test_an_insult_zeroes_the_policy_score() -> None:
    call = played(SHARMA, ("chup karo", {Tag.ABUSIVE}))
    assert score(call).policy_compliance == 0


def test_language_adaptation_counts_the_turns_after_the_switch() -> None:
    call = played(
        LAKSHMI,
        ("not my problem madam", {Tag.DISMISSIVE}),  # 70 → 88: she switches to Tamil
        ("romba sorry madam", {Tag.FOLLOWED_LANGUAGE_SWITCH, Tag.APOLOGISED}),
        ("sorry madam", {Tag.APOLOGISED}),
    )
    assert [turn.language_switched for turn in call.turns] == [False, True, True]
    assert score(call).language_adaptation == 50


def test_language_adaptation_is_not_tested_when_the_customer_never_switches() -> None:
    assert score(played(SHARMA, ("sorry", {Tag.APOLOGISED}))).language_adaptation is None


def test_winning_faster_is_more_efficient() -> None:
    fast = score(played(SHARMA, *GOOD_CALL, seconds_per_turn=10)).efficiency
    slow = score(played(SHARMA, *GOOD_CALL, seconds_per_turn=40)).efficiency
    assert fast > slow


def test_a_lost_call_gets_efficiency_for_how_far_it_calmed_the_customer() -> None:
    assert score(played(SHARMA, ("sorry", {Tag.APOLOGISED}))).efficiency == 9  # 10 of 55 points


def test_every_monologue_costs_10_efficiency() -> None:
    rambling = " ".join(["sorry"] * 41)
    turns = ((rambling, {Tag.USED_NAME, Tag.APOLOGISED, Tag.ACKNOWLEDGED_FEELING}), *GOOD_CALL[1:])
    assert score(played(SHARMA, *turns)).efficiency == 73


def test_the_total_ignores_dimensions_that_were_not_tested() -> None:
    scores = Scores(
        empathy=80,
        resolution=60,
        policy_compliance=100,
        language_adaptation=None,
        efficiency=40,
    )
    assert scores.total == 70


def test_a_call_with_no_turns_cannot_be_scored() -> None:
    with pytest.raises(ValueError):
        score(Call(SHARMA, ScriptedActor([]), ScriptedJudge([]), "hello?"))


def test_the_best_line_must_not_also_do_harm() -> None:
    call = played(
        SHARMA,
        ("i am sorry", {Tag.APOLOGISED}),
        (
            "sorry sharma ji i understand ticket raised but these things happen",
            {
                Tag.APOLOGISED,
                Tag.USED_NAME,
                Tag.ACKNOWLEDGED_FEELING,
                Tag.CONCRETE_NEXT_STEP,
                Tag.DISMISSIVE,
            },
        ),
    )
    best = best_line(call)
    assert best is not None and best.agent == "i am sorry"


def test_there_is_no_best_line_when_nothing_calmed_the_customer() -> None:
    assert best_line(played(SHARMA, ("hello", set()))) is None


def test_a_forbidden_promise_is_the_worst_line_even_if_another_angered_more() -> None:
    call = played(
        SHARMA,
        ("these things happen", {Tag.DISMISSIVE}),  # +15 anger
        ("refund aaj hi aa jayega", {Tag.FORBIDDEN_PROMISE}),  # +0 anger, but a strike
    )
    worst = worst_line(call)
    assert worst is not None and worst.agent == "refund aaj hi aa jayega"


def test_an_insult_is_the_worst_line_even_over_a_forbidden_promise() -> None:
    call = played(
        SHARMA,
        ("refund aaj hi aa jayega", {Tag.FORBIDDEN_PROMISE}),
        ("chup karo", {Tag.ABUSIVE}),
    )
    worst = worst_line(call)
    assert worst is not None and worst.agent == "chup karo"


def tip(quote: str) -> Tip:
    return Tip(quote=quote, advice="do better", try_saying="sorry sharma ji")


def test_coach_keeps_two_tips_and_blanks_quotes_the_agent_never_said() -> None:
    call = played(SHARMA, ("these things happen", {Tag.DISMISSIVE}))
    llm = ScriptedCoach([tip("These  things"), tip("i will fix it"), tip("")])
    tips = asyncio.run(coach(llm, call, score(call)))
    assert [t.quote for t in tips] == ["These  things", ""]


def test_coach_sees_the_policy_and_the_judged_call() -> None:
    call = played(SHARMA, ("these things happen", {Tag.DISMISSIVE}))
    prompt = system_prompt(call)
    for text in [*SHARMA.policy.allowed_remedies, *SHARMA.policy.forbidden_promises]:
        assert text in prompt
    assert "$" not in prompt
    summary = call_summary(call, score(call))
    assert "Agent: these things happen  [judge: dismissive]" in summary
    assert "language adaptation" not in summary
