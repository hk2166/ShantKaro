"""Play a training call in the terminal: you type as the agent, the customer answers.

Run from backend/ (needs ANTHROPIC_API_KEY in .env):
  uv run shant sharma_uncle
  uv run shant rohan --seconds-per-turn 20

Type /quit to hang up. Each turn moves the call clock by --seconds-per-turn, because typing is
much slower than talking.
"""

import argparse
import asyncio
import json
import random
import time
from pathlib import Path

from dotenv import load_dotenv

from shant.agents.reporter import Scores, Tip, best_line, coach, score, worst_line
from shant.engine.state import Status
from shant.game.call import Call
from shant.llm.claude import COACH_SETTINGS, JUDGE_SETTINGS, ClaudeLLM
from shant.llm.provider import LLM, LLMRefusalError, StructuredLLM
from shant.scenarios.loader import load_all
from shant.scenarios.schema import Scenario
from shant.tags import Tag

ROOT = Path(__file__).resolve().parents[3]
TRANSCRIPTS = ROOT / "evals" / "transcripts"
METER_WIDTH = 20

SCORE_WIDTH = 10


def bar(value: int, width: int) -> str:
    filled = round(value / 100 * width)
    return "█" * filled + "░" * (width - filled)


def meter(call: Call, elapsed_s: float) -> str:
    state, dynamics = call.state, call.scenario.dynamics
    clock = f"{int(elapsed_s) // 60}:{int(elapsed_s) % 60:02d}"
    limit = f"{dynamics.time_limit_s // 60}:{dynamics.time_limit_s % 60:02d}"
    return (
        f"anger [{bar(state.anger, METER_WIDTH)}] {state.anger:3d} · {clock} / {limit} · "
        f"strikes {state.strikes}/{dynamics.max_strikes}"
    )


def brief(scenario: Scenario) -> str:
    lines = [
        f"\n=== {scenario.persona.name} · {scenario.title} ({scenario.company.name}) ===",
        f"{scenario.grievance.summary}\n",
        "You may offer:",
        *(f"  + {item}" for item in scenario.policy.allowed_remedies),
        "You must not:",
        *(f"  - {item}" for item in scenario.policy.forbidden_promises),
        "",
        "Calm the customer down and agree a fix. Type /quit to hang up.",
    ]
    return "\n".join(lines)


OUTCOMES = {
    Status.WON: "🎉 The customer calmed down and accepted your fix. You win!",
    Status.TIMED_OUT: "⏱  Time's up. The customer is still unhappy.",
    Status.ENDED_BY_TRAINEE: "You ended the call.",
}


def outcome(call: Call) -> str:
    if call.state.status is Status.HUNG_UP:
        last = call.state.turns[-1].tags if call.state.turns else frozenset()
        if Tag.ABUSIVE in last:
            return "📞 You insulted the customer, so they hung up. That ends a real call too."
        if call.state.strikes >= call.scenario.dynamics.max_strikes:
            return "📞 Too many promises the company can't keep. The customer hung up."
        return "📞 The customer lost patience and hung up."
    return OUTCOMES[call.state.status]


async def play(
    scenario: Scenario,
    seconds_per_turn: float,
    actor_llm: LLM | None = None,
    judge_llm: StructuredLLM | None = None,
) -> Call:
    call = Call(
        scenario,
        actor_llm or ClaudeLLM(),
        judge_llm or ClaudeLLM(JUDGE_SETTINGS),
        random.choice(scenario.opening_lines),
    )
    print(brief(scenario))
    print(f"\n{scenario.persona.name}: {call.actor.opening_line}")
    print(meter(call, 0))

    elapsed = 0.0
    while not call.state.finished:
        try:
            line = (await asyncio.to_thread(input, "\nyou> ")).strip()
        except EOFError:
            call.hang_up()
            break
        if not line:
            continue
        if line in {"/quit", "/hangup"}:
            call.hang_up()
            break
        elapsed += seconds_per_turn
        print(f"{scenario.persona.name}: ", end="", flush=True)
        try:
            turn = await call.respond(
                line.lower(), elapsed, on_text=lambda text: print(text, end="", flush=True)
            )
        except LLMRefusalError:
            print("(the customer went quiet; try rephrasing)")
            continue
        print()
        tags = ", ".join(f'{e.tag} ("{e.quote}")' for e in turn.verdict.tags) or "no tags"
        print(f"  judge: {tags} → anger {turn.anger_before} → {turn.anger_after}")
        call.tick(elapsed)
        print(meter(call, elapsed))

    print(f"\n{outcome(call)}")
    return call


def report_card(call: Call, scores: Scores) -> str:
    lines = [f"\n=== Report card: {scores.total}/100 ==="]
    for name, value in vars(scores).items():
        label = name.replace("_", " ")
        if value is None:
            lines.append(f"  {label:<20} not tested in this call")
        else:
            lines.append(f"  {label:<20} {bar(value, SCORE_WIDTH)} {value:3d}")
    for title, turn in (("Best line", best_line(call)), ("Worst line", worst_line(call))):
        if turn is not None:
            tags = ", ".join(evidence.tag for evidence in turn.verdict.tags)
            lines.append(
                f'{title}: "{turn.agent}" ({tags}; anger {turn.anger_before} → {turn.anger_after})'
            )
    return "\n".join(lines)


def tips_text(tips: list[Tip]) -> str:
    lines = ["\nCoaching tips:"]
    for number, tip in enumerate(tips, start=1):
        about = f'"{tip.quote}" → ' if tip.quote else ""
        lines += [f"  {number}. {about}{tip.advice}", f"     Try: {tip.try_saying}"]
    return "\n".join(lines)


async def debrief(call: Call, coach_llm: StructuredLLM | None = None) -> list[Tip]:
    """Show the scores straight away, then the coaching tips once the LLM has written them."""
    scores = score(call)
    print(report_card(call, scores))
    print("\nYour coach is writing tips...")
    try:
        tips = await coach(coach_llm or ClaudeLLM(COACH_SETTINGS), call, scores)
    except LLMRefusalError:
        print("(the coach had nothing to say this time)")
        return []
    print(tips_text(tips))
    return tips


def save(call: Call) -> Path:
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = TRANSCRIPTS / f"{call.scenario.id}_{call.state.status}_{stamp}.json"
    path.write_text(json.dumps(call.transcript(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> None:
    load_dotenv(ROOT / ".env")
    scenarios = load_all()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("scenario", choices=sorted(scenarios))
    parser.add_argument("--seconds-per-turn", type=float, default=15)
    parser.add_argument("--no-save", action="store_true", help="don't save the transcript")
    args = parser.parse_args()

    call = asyncio.run(play(scenarios[args.scenario], args.seconds_per_turn))
    if not call.turns:
        return
    # Save first, so the transcript survives even if the coach's API call fails.
    if not args.no_save:
        print(f"Transcript saved to {save(call)}")
    asyncio.run(debrief(call))


if __name__ == "__main__":
    main()
