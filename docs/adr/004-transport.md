# ADR-004: WebRTC (Pipecat SmallWebRTC) between browser and bot

- **Status:** Proposed (Oct 14 2026). The bot server starts and serves the client page on a laptop. A spoken test (laptop) and a phone test over a tunnel are still pending.
- **Deciders:** Hemant

## Context

The browser has to stream mic audio to the bot and play the customer's voice back with as little delay as possible. Pipecat offers WebRTC transports (SmallWebRTC, Daily) and a plain WebSocket transport.

## Decision

Use **SmallWebRTC**: a direct WebRTC connection from the browser to the bot process, with no third-party media service. During development the bot is served with Pipecat's runner and prebuilt client (`uv run python spikes/s4_echo_bot.py -t webrtc`, then open http://localhost:7860/client).

## Why WebRTC over a WebSocket

- **Echo cancellation and noise suppression come from the browser.** Without them, the customer's voice leaks back into the mic and gets transcribed as the trainee.
- **UDP with a jitter buffer** handles bad networks better than WebSocket's TCP, where one lost packet stalls everything behind it.
- **Opus audio compression** in WebRTC uses far less bandwidth than raw PCM over a WebSocket.

## Why not Daily

Daily is managed WebRTC and very reliable, but it's another account, another API key and another bill. SmallWebRTC is enough for one browser talking to one bot.

## Consequences and risks

- Some phone and corporate networks block direct UDP. A deployed version will likely need a **TURN server** (risk R7, Day 23). Test on a phone through a tunnel before relying on it.
- The fallback, if WebRTC can't be made reliable, is Pipecat's WebSocket transport, giving up echo cancellation.
- The browser can't talk to Gnani directly anyway (Gnani's auth uses headers browsers can't set), so all audio flows through our bot. That's fine, because the bot needs it for the pipeline.
