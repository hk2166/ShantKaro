# Shant Karo · web app

The browser side of the game: pick a customer, read the brief, take the call by voice, and get
a report card. It talks to the voice backend through the Pipecat client SDK (SmallWebRTC).

## Run it locally

Start the backend first, from the repo root (it needs `GNANI_API_KEY` and `ANTHROPIC_API_KEY`
in `.env`):

```bash
cd backend && uv run python -m shant.voice.pipeline -t webrtc
```

Then the app:

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:5173. Vite forwards `/scenarios`, `/start`, `/sessions`, `/reports` and
`/health` to the backend on port 7860, so the browser sees one origin. Use headphones: the
customer can hear their own voice through laptop speakers.

## What the backend gives the app

| Route | Use |
|---|---|
| `GET /scenarios` | The customers for the picker |
| `POST /start` | `{"transport": "webrtc", "body": {"scenario": "<id>"}}` → `{"sessionId"}`, or `{"error", "message"}` when a limit is hit |
| `/sessions/{id}/api/offer` | The WebRTC connection for that call (the SDK uses it) |
| `GET /reports/{id}` | The report card after the call; `202` while the coach is still writing |

During the call the server sends a `call_state` message after every turn (anger, strikes,
time, status, the Judge's tags), and the app sends `set_language` when the trainee switches
language.

## Checks

```bash
npm run lint && npm run build
```
