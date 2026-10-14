from dataclasses import replace
from itertools import pairwise

import pytest
from hypothesis import given
from hypothesis import strategies as st

from shant.engine.rules import MAX_ANGER, apply, end_by_trainee, start, tick
from shant.engine.state import GameState, Judgement, Status
from shant.scenarios.loader import load_all
from shant.scenarios.schema import Scenario
from shant.tags import CALMING, Tag

SCENARIOS = load_all()
SHARMA = SCENARIOS["sharma_uncle"]
LAKSHMI = SCENARIOS["lakshmi_aunty"]
ROHAN = SCENARIOS["rohan"]


def judged(*tags: Tag) -> Judgement:
    return Judgement(frozenset(tags))


def with_dynamics(scenario: Scenario, **changes: object) -> Scenario:
    return scenario.model_copy(update={"dynamics": scenario.dynamics.model_copy(update=changes)})


# --- unit tests: one rule each -------------------------------------------------------


def test_call_starts_at_the_scenarios_starting_anger() -> None:
    state = start(SHARMA)
    assert state == GameState(anger=75)
    assert not state.finished


def test_an_apology_lowers_anger_by_its_weight() -> None:
    state = apply(start(SHARMA), judged(Tag.APOLOGISED), SHARMA, elapsed_s=10)
    assert state.anger == 75 - 10


def test_tags_in_one_turn_add_up() -> None:
    state = apply(start(SHARMA), judged(Tag.APOLOGISED, Tag.USED_NAME), SHARMA, elapsed_s=10)
    assert state.anger == 75 - 10 - 3


def test_being_dismissive_raises_anger() -> None:
    state = apply(start(SHARMA), judged(Tag.DISMISSIVE), SHARMA, elapsed_s=10)
    assert state.anger == 75 + 15


def test_anger_never_goes_below_zero() -> None:
    scenario = with_dynamics(SHARMA, win_at_or_below=0)
    state = replace(start(scenario), anger=5)
    state = apply(state, judged(Tag.APOLOGISED), scenario, elapsed_s=10)
    assert state.anger == 0


def test_reaching_max_anger_hangs_up() -> None:
    state = replace(start(SHARMA), anger=90)
    state = apply(state, judged(Tag.BLAMED_CUSTOMER), SHARMA, elapsed_s=10)
    assert state.anger == MAX_ANGER
    assert state.status is Status.HUNG_UP


def test_forbidden_promise_adds_a_strike() -> None:
    state = apply(start(SHARMA), judged(Tag.FORBIDDEN_PROMISE), SHARMA, elapsed_s=10)
    assert state.strikes == 1
    assert state.status is Status.IN_PROGRESS


def test_too_many_strikes_hangs_up() -> None:
    state = start(ROHAN)
    for second in (10, 20):
        state = apply(state, judged(Tag.FORBIDDEN_PROMISE), ROHAN, elapsed_s=second)
    assert state.strikes == ROHAN.dynamics.max_strikes
    assert state.status is Status.HUNG_UP


def test_a_next_step_bundled_with_a_forbidden_promise_is_not_a_resolution() -> None:
    state = apply(
        start(SHARMA), judged(Tag.CONCRETE_NEXT_STEP, Tag.FORBIDDEN_PROMISE), SHARMA, elapsed_s=10
    )
    assert not state.resolution_offered


def test_calm_customer_without_a_resolution_is_not_a_win() -> None:
    state = replace(start(SHARMA), anger=25)
    state = apply(state, judged(Tag.APOLOGISED), SHARMA, elapsed_s=10)
    assert state.anger <= SHARMA.dynamics.win_at_or_below
    assert state.status is Status.IN_PROGRESS


def test_calm_customer_with_a_resolution_is_a_win() -> None:
    state = replace(start(SHARMA), anger=30)
    state = apply(state, judged(Tag.CONCRETE_NEXT_STEP), SHARMA, elapsed_s=10)
    assert state.anger == 15
    assert state.status is Status.WON


def test_a_resolution_offered_earlier_still_counts_when_the_customer_calms() -> None:
    state = apply(start(SHARMA), judged(Tag.CONCRETE_NEXT_STEP), SHARMA, elapsed_s=10)
    assert state.resolution_offered and state.status is Status.IN_PROGRESS
    for second in (20, 30, 40):
        state = apply(state, judged(Tag.APOLOGISED, Tag.ACKNOWLEDGED_FEELING), SHARMA, second)
    assert state.status is Status.WON


def test_the_clock_ends_the_call_at_the_time_limit() -> None:
    limit = SHARMA.dynamics.time_limit_s
    assert tick(start(SHARMA), SHARMA, elapsed_s=limit - 1).status is Status.IN_PROGRESS
    assert tick(start(SHARMA), SHARMA, elapsed_s=limit).status is Status.TIMED_OUT


def test_the_trainee_can_hang_up() -> None:
    assert end_by_trainee(start(SHARMA)).status is Status.ENDED_BY_TRAINEE


def test_lakshmi_switches_to_tamil_once_angry_and_stays_switched() -> None:
    state = start(LAKSHMI)
    assert not state.language_switched
    state = apply(state, judged(Tag.DISMISSIVE), LAKSHMI, elapsed_s=10)
    assert state.anger >= 85 and state.language_switched
    state = apply(state, judged(Tag.APOLOGISED, Tag.CONCRETE_NEXT_STEP), LAKSHMI, elapsed_s=20)
    assert state.anger < 85 and state.language_switched


def test_each_turn_is_recorded_for_the_report_card() -> None:
    state = apply(start(SHARMA), judged(Tag.APOLOGISED), SHARMA, elapsed_s=10)
    (turn,) = state.turns
    assert (turn.tags, turn.anger_before, turn.anger_after) == (frozenset({Tag.APOLOGISED}), 75, 65)


@pytest.mark.parametrize(
    "finished",
    [Status.WON, Status.HUNG_UP, Status.TIMED_OUT, Status.ENDED_BY_TRAINEE],
)
def test_a_finished_call_never_changes(finished: Status) -> None:
    state = replace(start(SHARMA), status=finished)
    assert apply(state, judged(Tag.DISMISSIVE), SHARMA, elapsed_s=999) is state
    assert tick(state, SHARMA, elapsed_s=999) is state
    assert end_by_trainee(state) is state


# --- property tests: rules that must hold for any sequence of turns --------------------

scenarios = st.sampled_from(sorted(SCENARIOS)).map(SCENARIOS.__getitem__)
tag_sets = st.frozensets(st.sampled_from(list(Tag)))
calming_sets = st.frozensets(st.sampled_from(sorted(CALMING)))


def play(scenario: Scenario, turns: list[frozenset[Tag]]) -> list[GameState]:
    states = [start(scenario)]
    for index, tags in enumerate(turns, start=1):
        states.append(apply(states[-1], Judgement(tags), scenario, elapsed_s=index * 5.0))
    return states


@given(scenarios, st.lists(tag_sets, max_size=40))
def test_anger_always_stays_between_0_and_100(scenario: Scenario, turns) -> None:
    assert all(0 <= state.anger <= MAX_ANGER for state in play(scenario, turns))


@given(scenarios, st.lists(calming_sets, max_size=40))
def test_good_behaviour_never_makes_a_customer_angrier(scenario: Scenario, turns) -> None:
    states = play(scenario, turns)
    assert all(after.anger <= before.anger for before, after in pairwise(states))


@given(scenarios, st.lists(tag_sets, max_size=40))
def test_strikes_count_forbidden_promises_made_during_the_call(scenario: Scenario, turns) -> None:
    states = play(scenario, turns)
    final = states[-1]
    applied = [turn for turn, before in zip(turns, states[:-1], strict=True) if not before.finished]
    assert final.strikes == sum(Tag.FORBIDDEN_PROMISE in turn for turn in applied)


@given(scenarios, st.lists(tag_sets, max_size=40))
def test_once_finished_a_call_stays_exactly_the_same(scenario: Scenario, turns) -> None:
    states = play(scenario, turns)
    first_finished = next((i for i, s in enumerate(states) if s.finished), None)
    if first_finished is not None:
        assert all(s is states[first_finished] for s in states[first_finished:])


@given(scenarios, st.lists(tag_sets, max_size=40))
def test_a_win_always_means_calm_and_a_resolution(scenario: Scenario, turns) -> None:
    for state in play(scenario, turns):
        if state.status is Status.WON:
            assert state.anger <= scenario.dynamics.win_at_or_below
            assert state.resolution_offered


@given(scenarios, st.floats(min_value=0, max_value=10_000, allow_nan=False))
def test_every_call_ends_by_the_time_limit(scenario: Scenario, elapsed: float) -> None:
    state = tick(start(scenario), scenario, elapsed)
    assert state.finished == (elapsed >= scenario.dynamics.time_limit_s)
