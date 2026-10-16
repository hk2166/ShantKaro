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

from shant.engine.state import Status
from shant.game.call import Call
from shant.llm.claude import JUDGE_SETTINGS, ClaudeLLM
from shant.llm.provider import LLM, LLMRefusalError, StructuredLLM
from shant.scenarios.loader import load_all
from shant.scenarios.schema import Scenario

ROOT = Path(__file__).resolve().parents[3]
TRANSCRIPTS = ROOT / "evals" / "transcripts"
METER_WIDTH = 20


def meter(call: Call, elapsed_s: float) -> str:
    state, dynamics = call.state, call.scenario.dynamics
    filled = round(state.anger / 100 * METER_WIDTH)
    bar = "█" * filled + "░" * (METER_WIDTH - filled)
    clock = f"{int(elapsed_s) // 60}:{int(elapsed_s) % 60:02d}"
    limit = f"{dynamics.time_limit_s // 60}:{dynamics.time_limit_s % 60:02d}"
    return (
        f"anger [{bar}] {state.anger:3d} · {clock} / {limit} · "
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
    if call.turns and not args.no_save:
        print(f"Transcript saved to {save(call)}")


if __name__ == "__main__":
    main()
