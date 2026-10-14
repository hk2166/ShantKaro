# ADR-003: Claude Sonnet 5.5 for the customer AI

- **Status:** Accepted, Oct 14 2026
- **Deciders:** Hemant

## Context

The customer AI (the Actor) plays the angry caller on every turn of a live voice call. Two requirements decide the model:

1. **Speed.** The turn budget is 1.8 s P50 from the trainee going quiet to the customer's voice starting (task.md §5.2). Speech-to-text already uses about 0.75 s (S1: silence setting 500 ms + ~240 ms). So the LLM needs to produce its **first full sentence in about 1 s**, the moment text-to-speech can start.
2. **Voice-safe writing.** Each customer must write their language the way Gnani's TTS reads it correctly. S0 showed that Hindi written in Roman letters is mispronounced ("log" was read as "lock"). So Sharma Uncle must write Hindi in Devanagari and English words in Latin, and Lakshmi Aunty must write Tamil in Tamil script.

## What was measured (spike S3)

Each model played all three customers through a 10-turn scripted call (`backend/spikes/s3_scripts/`, run with `s3_llm.py`). That's 30 replies per model, timed from the request to the first full sentence. Each script contains one deliberate agent mistake at turn 4 (dismissive, or a forbidden promise).

| Model | Setting | First sentence P50 | P95 | First token P50 |
|---|---|---|---|---|
| Claude Opus 5.5 | effort `low` (thinking always on) | 2,576 ms | 7,447 ms | 2,328 ms |
| Claude Haiku 5.5 | effort `low`, thinking `disabled` | 1,001 ms | 1,922 ms | 770 ms |
| **Claude Sonnet 5.5** | effort `low`, thinking `between_tools` | **1,102 ms** | **1,614 ms** | 756 ms |

Measured from a laptop in India, one run per model.

## Decision

Use **Claude Sonnet 5.5** (`claude-sonnet-5-5`) for the customer, with:
- `output_config: {effort: "low"}`
- `thinking: {type: "between_tools"}` (Sonnet 5.5's way to turn thinking off; `disabled` is rejected with a 400)
- server-side `fallbacks: "default"` with the `server-side-fallback-2026-07-01` beta header

## Why not the others

- **Opus 5.5** played the customers best, but it's about 1.5 s over budget at P50 and over 7 s at P95. Its thinking can't be switched off; effort `low` is the floor. A 3–8 second silence on every turn would kill the call.
- **Haiku 5.5** is as fast as Sonnet at P50, but it ignored the script instruction: Sharma Uncle replied in Roman Hindi (*"Namaste. Dekhiye Rahul ji, main teesri baar call kar raha hoon…"*), which the TTS mispronounces. Its replies were also flatter and less in character, and its P95 (1.9 s) is worse than Sonnet's.
- **Sonnet 5.5** kept every script rule, stayed in character, and pushed back on cue at turn 4. For example, Rohan to a forbidden promise: *"'Right now today itself' sounds nice, but I've heard this song before, guru."* It also has the steadiest slow end of the three.

## Consequences

- **Cost:** about $0.03–0.05 per 3-minute call: roughly 12k input and 1k output tokens at $2 / $10 per million. That's about $15–25 for 500 public calls. Caching the customer's fixed instructions lowers the input part. Haiku would cost about 20× less, if it ever learns to keep the script rule.
- **Pipecat integration:** Pipecat 1.5's `AnthropicLLMService` predates these settings (ADR-001). `thinking`, `output_config` and `fallbacks` have to go through its `extra` setting, and we must check that its own `betas` value doesn't overwrite the fallback beta. If that doesn't work cleanly, write a small custom LLM service.
- **`between_tools` limits:** only valid at effort `high` or below, takes no other thinking fields, and doesn't allow per-message effort changes. Fine for a customer that never needs deep reasoning.
- **Made-up facts:** all three models invented order IDs, because the S3 prompts don't include the scenario's facts. The real Actor prompt (Day 9) feeds in `grievance.facts` from the scenario file. Re-check this once it does.
- **Latency is still tight.** About 0.75 s STT + 1.1 s LLM + ~0.2 s TTS ≈ 2 s, slightly over the 1.8 s P50 target. Day 9's levers:
  - keep replies short;
  - start TTS on the first clause (comma) instead of the first full sentence;
  - cache the system prompt;
  - deploy the bot close to the API.
- **The Judge can use a different model.** It runs off the hot path while the customer is speaking (§5.1), so it can afford Opus-level quality. That's decided on Day 10.
- **Re-run S3** if the Actor prompt changes substantially, or when a new model version ships.
