"""S3: how fast, and how well, does an LLM play the angry customer?

Run from backend/ (needs ANTHROPIC_API_KEY in .env):
  uv run python spikes/s3_llm.py                                   # default model, all 3 personas
  uv run python spikes/s3_llm.py --model <model-id> --effort low
  uv run python spikes/s3_llm.py --model <model-id> --effort none  # model without effort support
  uv run python spikes/s3_llm.py --persona rohan
  uv run python spikes/s3_llm.py --model claude-haiku-5-5 --effort low --thinking disabled
  uv run python spikes/s3_llm.py --model claude-sonnet-5-5 --effort low --thinking between_tools

Replays each 10-turn script in spikes/s3_scripts/ as a real conversation: every trainee line
is sent with the history so far, and the customer's reply is streamed. For each turn it
measures the time to the first text token and to the first full sentence (when TTS can start
speaking). Transcripts go to out/s3/ so the replies can be rated for quality.
"""

import argparse
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

import anthropic
from anthropic.types.beta import BetaMessageParam
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).parent / "s3_scripts"
OUT = ROOT / "backend" / "out" / "s3"
load_dotenv(ROOT / ".env")

DEFAULT_MODEL = "claude-opus-5-5"
# Models that accept server-side `fallbacks: "default"`; others reject the parameter.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
SENTENCE_END = re.compile(r"[.!?।]")


def stream_reply(
    client: anthropic.Anthropic,
    model: str,
    effort: str,
    thinking: str,
    system: str,
    history: list[BetaMessageParam],
) -> dict:
    extra: dict = {}
    if effort != "none":
        extra["output_config"] = {"effort": effort}
    if thinking != "default":
        extra["thinking"] = {"type": thinking}
    if model in FALLBACK_MODELS:
        extra["betas"] = ["server-side-fallback-2026-07-01"]
        extra["fallbacks"] = "default"

    start = time.perf_counter()
    first_token = first_sentence = None
    text = ""
    with client.beta.messages.stream(
        model=model, max_tokens=16000, system=system, messages=history, **extra
    ) as stream:
        for chunk in stream.text_stream:
            now = time.perf_counter()
            first_token = first_token or now
            text += chunk
            if first_sentence is None and SENTENCE_END.search(text):
                first_sentence = now
        final = stream.get_final_message()

    def ms(moment: float | None) -> int | None:
        return round((moment - start) * 1000) if moment else None

    return {
        "first_token_ms": ms(first_token),
        "first_sentence_ms": ms(first_sentence),
        "total_ms": ms(time.perf_counter()),
        "output_tokens": final.usage.output_tokens,
        "stop_reason": final.stop_reason,
        "text": text.strip(),
    }


def run_script(
    client: anthropic.Anthropic, model: str, effort: str, thinking: str, script: dict
) -> list[dict]:
    print(f"\n=== {script['persona']} ===")
    history: list[BetaMessageParam] = []
    turns = []
    for index, line in enumerate(script["trainee_lines"], start=1):
        history.append({"role": "user", "content": line})
        turn = stream_reply(client, model, effort, thinking, script["system"], history)
        turn["trainee"] = line
        turns.append(turn)
        print(
            f"{index:2d}. first sentence {turn['first_sentence_ms']} ms "
            f"(first token {turn['first_token_ms']} ms, {turn['output_tokens']} tokens)"
        )
        print(f"    agent:    {line}")
        print(f"    customer: {turn['text'] or '(no text: ' + str(turn['stop_reason']) + ')'}")
        if not turn["text"]:
            break
        history.append({"role": "assistant", "content": turn["text"]})
    return turns


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default="low", help="low | medium | high | none")
    parser.add_argument("--persona", help="script name, e.g. sharma_uncle (default: all)")
    parser.add_argument(
        "--thinking",
        default="default",
        choices=["default", "adaptive", "disabled", "between_tools"],
    )
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY in .env first (see .env.example).")

    paths = sorted(SCRIPTS.glob(f"{args.persona or '*'}.json"))
    if not paths:
        sys.exit(f"No script matches {args.persona!r} in {SCRIPTS}")

    client = anthropic.Anthropic()
    OUT.mkdir(parents=True, exist_ok=True)
    all_turns = []
    for path in paths:
        script = json.loads(path.read_text())
        try:
            turns = run_script(client, args.model, args.effort, args.thinking, script)
        except anthropic.APIStatusError as error:
            sys.exit(f"API error {error.status_code}: {error.message}")
        all_turns.extend(turns)
        result_path = OUT / f"{args.model}_{args.effort}_{args.thinking}_{path.stem}.json"
        result_path.write_text(json.dumps(turns, ensure_ascii=False, indent=2))

    sentence_times = [t["first_sentence_ms"] for t in all_turns if t["first_sentence_ms"]]
    if sentence_times:
        p95 = statistics.quantiles(sentence_times, n=20)[-1] if len(sentence_times) > 1 else None
        print(
            f"\n{args.model} (effort {args.effort}, thinking {args.thinking}), "
            f"{len(sentence_times)} turns: "
            f"first sentence P50 {statistics.median(sentence_times):.0f} ms, P95 {p95} ms"
        )
    print(f"Transcripts saved in {OUT}")


if __name__ == "__main__":
    main()
