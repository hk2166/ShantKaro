"""S3: how fast does an LLM start answering as the angry customer?

Run from backend/ (needs ANTHROPIC_API_KEY in .env):
  uv run python spikes/s3_llm.py                                    # default model, 5 runs
  uv run python spikes/s3_llm.py --model <model-id> --effort low --runs 5
  uv run python spikes/s3_llm.py --model <model-id> --effort none   # model without effort support

Streams Sharma Uncle's reply to one trainee line, and measures the time to the first text
token and to the first full sentence. The first full sentence is the moment TTS can start
speaking, so it's the number that goes into the latency budget (task.md §5.2).
"""

import argparse
import os
import re
import statistics
import sys
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DEFAULT_MODEL = "claude-opus-5-5"
# Models that accept server-side `fallbacks: "default"`; others reject the parameter.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}

SYSTEM = """You are Sharma Uncle, a 58-year-old retired bank clerk from Lucknow, on a \
support call with BharatKart. You returned a mixer grinder three weeks ago and your refund \
of ₹4,299 still hasn't arrived. You are angry, you've called twice already, and you speak \
Hinglish.

Say only what you would say out loud on the phone: one to three short sentences. Write \
Hindi words in Devanagari and English words in Latin letters. No stage directions, emojis \
or formatting."""

TRAINEE_LINE = "sir main aapki problem samajh sakta hoon aapka order id bata dijiye please"
SENTENCE_END = re.compile(r"[.!?।]")


def run_once(client: anthropic.Anthropic, model: str, effort: str) -> dict:
    extra: dict = {}
    if effort != "none":
        extra["output_config"] = {"effort": effort}
    if model in FALLBACK_MODELS:
        extra["betas"] = ["server-side-fallback-2026-07-01"]
        extra["fallbacks"] = "default"

    start = time.perf_counter()
    first_token = first_sentence = None
    text = ""
    with client.beta.messages.stream(
        model=model,
        max_tokens=16000,
        system=SYSTEM,
        messages=[{"role": "user", "content": TRAINEE_LINE}],
        **extra,
    ) as stream:
        for chunk in stream.text_stream:
            now = time.perf_counter()
            first_token = first_token or now
            text += chunk
            if first_sentence is None and SENTENCE_END.search(text):
                first_sentence = now
        final = stream.get_final_message()
    end = time.perf_counter()

    def ms(moment: float | None) -> int | None:
        return round((moment - start) * 1000) if moment else None

    return {
        "first_token_ms": ms(first_token),
        "first_sentence_ms": ms(first_sentence),
        "total_ms": ms(end),
        "output_tokens": final.usage.output_tokens,
        "stop_reason": final.stop_reason,
        "text": text.strip(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default="low", help="low | medium | high | none")
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY in .env first (see .env.example).")

    client = anthropic.Anthropic()
    results = []
    for index in range(1, args.runs + 1):
        try:
            result = run_once(client, args.model, args.effort)
        except anthropic.APIStatusError as error:
            sys.exit(f"API error {error.status_code}: {error.message}")
        results.append(result)
        print(
            f"run {index}: first token {result['first_token_ms']} ms, "
            f"first sentence {result['first_sentence_ms']} ms, total {result['total_ms']} ms, "
            f"{result['output_tokens']} tokens, {result['stop_reason']}"
        )
        print(f"   {result['text']}")

    def median(field: str) -> float | None:
        values = [r[field] for r in results if r[field] is not None]
        return statistics.median(values) if values else None

    print(
        f"\n{args.model} (effort {args.effort}), median of {len(results)}: "
        f"first token {median('first_token_ms')} ms, "
        f"first sentence {median('first_sentence_ms')} ms, total {median('total_ms')} ms"
    )


if __name__ == "__main__":
    main()
