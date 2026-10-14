# ADR-001: Pipecat (pinned to 1.5.0) for the voice pipeline

- **Status:** Accepted, Oct 14 2026
- **Deciders:** Hemant

## Context

The game needs a real-time voice loop: browser mic → speech-to-text → customer brain (LLM) → text-to-speech → browser speaker, with barge-in. Gnani maintains plugins for two frameworks, Pipecat and LiveKit Agents.

Spikes S1 and S4 found:
- `pipecat-gnani` 0.5.12 crashes on import with the current Pipecat (1.12): `cannot import name '_NotGiven'`. It's documented as tested with Pipecat 1.5.0.
- Pinned to `pipecat-ai==1.5.0`, it installs and works. It also pulls `websockets` down to 15.0.1, which our spikes are compatible with.
- The plugin's STT service can't set VAD headers (`x-min-silence-ms`, `x-vad-threshold`, `x-max-speech-s`), which S1 showed we need.

## Decision

Use **Pipecat, pinned to 1.5.0**, with `pipecat-gnani` for Gnani STT and TTS. Subclass the plugin's STT service to add the VAD headers.

## Why not LiveKit Agents

- LiveKit needs a LiveKit media server (self-hosted or LiveKit Cloud) between the browser and the bot. That's one more service to run, secure and pay for.
- Pipecat runs the whole pipeline in one Python process, and its SmallWebRTC transport talks to the browser directly (ADR-004).
- Both have Gnani plugins, so speech quality doesn't differ.

## Consequences

- We're seven minor versions behind Pipecat's latest. Upgrading means waiting for `pipecat-gnani` to support it, or writing our own Gnani services. Accepted for a 4-week project.
- `websockets` is held at 15.x.
- Pipecat's `AnthropicLLMService` in 1.5 predates Claude Opus 5.5: it only knows `thinking` with `budget_tokens`, and has no effort setting. It does pass an `extra` dict into the request, so `output_config.effort` can go through there. Day 6 must verify that its own `betas` value doesn't overwrite ours (the fallback beta).
- `pipecat-ai[webrtc]` installs both `av` and `opencv-python`, which bundle conflicting `libavdevice` copies. macOS warns that this "may cause spurious casting failures and mysterious crashes". Watch for it; we don't use video, so dropping opencv is an option.
