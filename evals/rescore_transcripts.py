"""Re-score saved transcripts after a deliberate change to the game rules.

Run from backend/:
  uv run python ../evals/rescore_transcripts.py           # show what would change
  uv run python ../evals/rescore_transcripts.py --write   # rewrite the files

The replay test (tests/test_call.py) checks that every saved game still ends the same way.
When a rule changes on purpose, that test fails for the games the rule affects. This script
replays each game's recorded Judge tags through the current engine and updates the anger,
strikes and ending. If the call now ends sooner, the turns after the new ending are dropped.
The agent's and customer's words are never changed.
"""

import argparse
import json
from pathlib import Path

from shant.engine.rules import apply, start
from shant.engine.state import Judgement
from shant.scenarios.loader import load_all
from shant.tags import Tag

TRANSCRIPTS = Path(__file__).resolve().parent / "transcripts"


def rescore(data: dict) -> dict:
    scenario = load_all()[data["scenario"]]
    state = start(scenario)
    turns = []
    for turn in data["turns"]:
        if state.finished:
            break
        before = state
        tags = frozenset(Tag(evidence["tag"]) for evidence in turn["tags"])
        state = apply(state, Judgement(tags), scenario, turn["elapsed_s"])
        turns.append(
            {
                **turn,
                "anger_before": before.anger,
                "anger_after": state.anger,
                "language_switched": before.language_switched,
            }
        )
    return {
        **data,
        "status": str(state.status),
        "final_anger": state.anger,
        "strikes": state.strikes,
        "turns": turns,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--write", action="store_true", help="rewrite the changed files")
    args = parser.parse_args()

    changed = 0
    for path in sorted(TRANSCRIPTS.glob("*.json")):
        old = json.loads(path.read_text(encoding="utf-8"))
        new = rescore(old)
        if [t["anger_after"] for t in new["turns"]] == [t["anger_after"] for t in old["turns"]]:
            continue
        changed += 1
        print(f"{path.name}: {old['status']} → {new['status']}")
        print(f"  anger {[t['anger_after'] for t in old['turns']]}")
        print(f"     →  {[t['anger_after'] for t in new['turns']]}")
        if args.write:
            path.write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{changed} transcript(s) {'rewritten' if args.write else 'would change'}.")


if __name__ == "__main__":
    main()
