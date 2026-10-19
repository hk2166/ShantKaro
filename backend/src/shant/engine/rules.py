"""Game rules: how a judged trainee turn, or the passing of time, changes a call.

Every function is pure: it takes a state and returns a new one. A finished call never
changes, so a late judgement or timer tick can't revive or re-score it.

Two rules override the scenario's weights:
- An insult (`abusive`) ends the call at once: the customer hangs up, as a real one would.
- A turn with a forbidden promise earns no calming credit, even if it also offers a real
  next step. Over-promising calms people in the moment, which is exactly why it's forbidden,
  so the game must never reward it.
"""

from dataclasses import replace

from shant.engine.state import GameState, Judgement, Status, Turn
from shant.scenarios.schema import Scenario
from shant.tags import CALMING, Tag

MAX_ANGER = 100


def start(scenario: Scenario) -> GameState:
    switch = scenario.dynamics.language_switch
    anger = scenario.dynamics.starting_anger
    return GameState(anger=anger, language_switched=switch is not None and anger >= switch.at_anger)


def anger_change(tags: frozenset[Tag], scenario: Scenario) -> int:
    """How much one judged turn moves anger, before clamping to 0–100."""
    counted = tags - CALMING if Tag.FORBIDDEN_PROMISE in tags else tags
    return sum(scenario.dynamics.tag_weights.get(tag, 0) for tag in counted)


def apply(
    state: GameState, judgement: Judgement, scenario: Scenario, elapsed_s: float
) -> GameState:
    if state.finished:
        return state
    dynamics = scenario.dynamics
    abusive = Tag.ABUSIVE in judgement.tags
    change = anger_change(judgement.tags, scenario)
    anger = MAX_ANGER if abusive else min(MAX_ANGER, max(0, state.anger + change))
    forbidden = Tag.FORBIDDEN_PROMISE in judgement.tags
    offered = Tag.CONCRETE_NEXT_STEP in judgement.tags and not forbidden and not abusive
    switch = dynamics.language_switch
    updated = replace(
        state,
        anger=anger,
        strikes=state.strikes + (1 if forbidden else 0),
        resolution_offered=state.resolution_offered or offered,
        language_switched=state.language_switched
        or (switch is not None and anger >= switch.at_anger),
        elapsed_s=max(state.elapsed_s, elapsed_s),
        turns=(*state.turns, Turn(judgement.tags, state.anger, anger)),
    )
    return replace(updated, status=_status(updated, scenario))


def tick(state: GameState, scenario: Scenario, elapsed_s: float) -> GameState:
    """Advance the call clock with no trainee turn; ends the call when time runs out."""
    if state.finished:
        return state
    updated = replace(state, elapsed_s=max(state.elapsed_s, elapsed_s))
    return replace(updated, status=_status(updated, scenario))


def end_by_trainee(state: GameState) -> GameState:
    return state if state.finished else replace(state, status=Status.ENDED_BY_TRAINEE)


def _status(state: GameState, scenario: Scenario) -> Status:
    dynamics = scenario.dynamics
    if state.anger >= MAX_ANGER or state.strikes >= dynamics.max_strikes:
        return Status.HUNG_UP
    if state.anger <= dynamics.win_at_or_below and state.resolution_offered:
        return Status.WON
    if state.elapsed_s >= dynamics.time_limit_s:
        return Status.TIMED_OUT
    return Status.IN_PROGRESS
