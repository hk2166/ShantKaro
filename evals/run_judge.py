"""Measure the Judge against hand-labelled agent lines.

Run from backend/ (needs ANTHROPIC_API_KEY in .env):
  uv run python ../evals/run_judge.py                                   # evals/judge_labels.jsonl
  uv run python ../evals/run_judge.py ../evals/judge_labels.example.jsonl
  uv run python ../evals/run_judge.py --effort low
  uv run python ../evals/run_judge.py --model claude-sonnet-5-5 --thinking between_tools

Each line of the labels file is one JSON object:
  {"id": "s01", "scenario": "sharma_uncle", "customer": "...", "agent": "...",
   "tags": ["apologised", "used_name"], "switched": false, "note": "optional"}
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv

from shant.agents.judge import Verdict, judge
from shant.evaluation import macro_f1, score_tags
from shant.llm.claude import JUDGE_SETTINGS, ClaudeLLM, ClaudeSettings
from shant.llm.provider import LLMRefusalError
from shant.scenarios.loader import load_all
from shant.tags import Tag

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LABELS = ROOT / "evals" / "judge_labels.jsonl"
OUT = ROOT / "backend" / "out" / "judge_eval.json"
CONCURRENCY = 4
load_dotenv(ROOT / ".env")


def load_labels(path: Path) -> list[dict]:
    if not path.exists():
        sys.exit(
            f"No labels file at {path}. Write it first (one JSON object per line), "
            "starting from evals/judge_labels.example.jsonl."
        )
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    scenarios = load_all()
    for row in rows:
        if row["scenario"] not in scenarios:
            sys.exit(f"{row['id']}: unknown scenario {row['scenario']!r}")
        for tag in row["tags"]:
            if tag not in Tag:
                sys.exit(f"{row['id']}: unknown tag {tag!r}")
    return rows


async def judge_all(rows: list[dict], settings: ClaudeSettings) -> list[tuple[Verdict, float]]:
    llm = ClaudeLLM(settings)
    scenarios = load_all()
    gate = asyncio.Semaphore(CONCURRENCY)

    async def one(row: dict) -> tuple[Verdict, float]:
        async with gate:
            start = time.perf_counter()
            try:
                verdict = await judge(
                    llm,
                    scenarios[row["scenario"]],
                    row["customer"],
                    row["agent"],
                    row.get("switched", False),
                )
            except LLMRefusalError:
                verdict = Verdict(tags=[])
            return verdict, time.perf_counter() - start

    return await asyncio.gather(*(one(row) for row in rows))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("labels", nargs="?", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--model", default=JUDGE_SETTINGS.model)
    parser.add_argument("--effort", default=JUDGE_SETTINGS.effort)
    parser.add_argument("--thinking", default=JUDGE_SETTINGS.thinking, help="omit for adaptive")
    args = parser.parse_args()
    settings = replace(JUDGE_SETTINGS, model=args.model, effort=args.effort, thinking=args.thinking)

    rows = load_labels(args.labels)
    print(
        f"Judging {len(rows)} lines from {args.labels.name} with {settings.model} "
        f"(effort {settings.effort}, thinking {settings.thinking or 'adaptive'})..."
    )
    results = asyncio.run(judge_all(rows, settings))

    expected = [frozenset(Tag(tag) for tag in row["tags"]) for row in rows]
    predicted = [verdict.judgement().tags for verdict, _ in results]
    scores = score_tags(expected, predicted)

    print(f"\n{'tag':26s} {'support':>7s} {'precision':>9s} {'recall':>7s} {'F1':>5s}")
    for tag, score in scores.items():
        print(
            f"{tag:26s} {score.support:7d} {score.precision:9.2f} {score.recall:7.2f} "
            f"{score.f1:5.2f}"
        )
    seconds = sorted(elapsed for _, elapsed in results)
    p95 = statistics.quantiles(seconds, n=20)[-1] if len(seconds) > 1 else seconds[0]
    print(f"\nmacro-F1 {macro_f1(scores):.2f}  (target 0.80)")
    print(f"latency P50 {statistics.median(seconds):.1f} s, P95 {p95:.1f} s  (budget ~3 s)")

    mismatches = [
        (row, want, got, verdict)
        for row, want, got, (verdict, _) in zip(rows, expected, predicted, results, strict=True)
        if want != got
    ]
    print(f"\n{len(mismatches)} mismatches:")
    for row, want, got, verdict in mismatches:
        quotes = "; ".join(f"{e.tag}: {e.quote!r}" for e in verdict.tags)
        print(f"- {row['id']}: expected {sorted(want)} got {sorted(got)}")
        print(f"    agent: {row['agent']}")
        print(f"    quotes: {quotes or '(none)'}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    report = [
        {**row, "predicted": sorted(got), "quotes": verdict.model_dump()["tags"], "seconds": t}
        for row, got, (verdict, t) in zip(rows, predicted, results, strict=True)
    ]
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDetails saved to {OUT}")


if __name__ == "__main__":
    main()
