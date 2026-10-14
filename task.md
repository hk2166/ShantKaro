# Shant Karo — Engineering Plan

> A voice training simulator for call-centre agents. The trainee takes a live call from an
> AI customer who is angry, code-mixed and on a noisy line, and has to calm them down without
> breaking company policy. Built on Gnani AI's Prisma (speech-to-text) and Timbre
> (text-to-speech) for the Great Indian AI Internship Challenge.

- **Deadline:** submission by 11:59 PM IST, Tue Nov 10 2026 (our target: Sun Nov 8)
- **Demo post goes live:** Mon Nov 2, morning IST (shortlist = verified engagement on this post)
- **Status:** Planning (Oct 6)
- **Day-by-day checklist:** [day-plan.md](day-plan.md). This file is the spec it refers to.

---

## 1. Why this project

| Contest requirement | How Shant Karo meets it |
|---|---|
| Working app on Gnani models/APIs | Prisma v2.5 realtime STT + Timbre v2.5 realtime TTS are the core of every call |
| "Practical need for enterprises, developers or creators" | BPOs and support teams train thousands of agents through manual role-play; this automates it. BPOs and customer support are on Gnani's own industry/solution list |
| Shortlist decided by engagement | Anyone can try a 3-minute "calm the customer" challenge and share their score |
| Interview decides the offer | Real engineering to talk about: latency budget, deterministic game engine vs LLM, judge evals, cost controls |
| Synthetic data only | Fictional companies, personas, order IDs; no audio stored |

Award fit (max one): Mixed Vibes (code-mixed), Real Deal (real-world impact), Crowd Favourite, Demo Day Drop.

## 2. Goals, non-goals, success metrics

### Goals (v1)
1. A stranger lands on the site, picks a scenario and is on a voice call within 15 seconds.
2. Three polished scenarios in different languages (see §4.3).
3. A live anger meter driven by a deterministic engine, not by the LLM's mood.
4. A post-call report card with scores and quotes from the trainee's own words, plus a shareable card.
5. Measured, documented engineering: latency, judge accuracy, STT accuracy under noise, cost per call.

### Non-goals (v1) — say no to these until after Nov 10
- Real phone numbers / PSTN telephony
- User accounts or login (nickname only)
- Native mobile apps (mobile browser must work)
- Voice cloning
- More than 3 scenarios, or a scenario editor UI (scenarios are YAML files)
- Storing audio recordings
- Multiplayer / supervisor mode

### Success metrics
| Area | Metric | Target |
|---|---|---|
| Latency | Trainee end-of-speech → first customer audio, P50 / P95 | ≤ 1.8 s / ≤ 3.0 s |
| Judge | Macro-F1 on the labelled behaviour set (§7.2) | ≥ 0.80 |
| Robustness | Character breaks on the jailbreak suite (§7.3) | 0 of 30 |
| Reliability | Sessions that end cleanly (no crash/hang) | ≥ 98% |
| Product | Beta players who play a second round | ≥ 40% |
| Contest | Post live / submission sent | Nov 2 / Nov 8 |

## 3. Facts from Gnani's docs that shape the design

Verified from docs.gnani.ai on Oct 6 2026. Re-check if something behaves differently.

**Prisma STT, realtime WebSocket** (`wss://api.vachana.ai/stt/v3/stream`)
- Auth and all config go in **WebSocket upgrade headers** → browsers can't set them, so audio must be proxied through our backend (also keeps the key off the client).
- Raw PCM s16le mono, **exactly 1,024-byte frames at real-time cadence** (32 ms @ 16 kHz). Bursting degrades VAD.
- **Final transcripts only** (no partials today). Server-side VAD closes a segment, sends `processing`, then `transcript` (~300–500 ms after end of speech per Gnani's compliance guide).
- `x-min-silence-ms` (default 500) is the biggest end-of-turn latency lever. VAD headers are fixed per connection.
- **The Python SDK does not expose VAD headers** → may need a thin custom STT service using raw `websockets`.
- **One language per connection** (`lang_code`). Switching language = reconnect. `en-IN` accepts Hindi-English mixed audio and outputs Latin script; `hi-IN` outputs Devanagari.
- ITN (`x-format: transcribe`) turns spoken numbers/currency into digits; word boosting (`x-bias-list`) for domain words; session cap 15 min.

**Timbre TTS, realtime WebSocket** (`wss://api.vachana.ai/api/v1/tts`)
- One synthesis request at a time per connection; base64 audio chunks; `complete` message at the end.
- Controls: `voice` (42 voices), `language` (incl. `hi-en` Hinglish, `auto`), `speed` 0.85–1.15. **No SSML or emotion parameter is documented** → anger must come from voice choice, speed and how lines are written (risk R1).
- Numbers, IDs and currency should be passed as spoken words (Input Formatting Guide).
- **S2 finding (Oct 12):** `container="mp3"` at 24 kHz returns HTTP 500 once the audio is a few seconds long. WAV at 24 kHz and MP3 at 16 kHz work. The game uses raw PCM over WebSocket, but any TTS call needs a fallback for 5xx errors so a call never goes silent.

**Integrations:** `pipecat-gnani` (tested with Pipecat v1.5.0; WebSocket TTS is an `InterruptibleTTSService` → barge-in support) and `livekit-plugins-gnani`.
- **S1 finding (Oct 11):** `pipecat-gnani` 0.5.12 can't set VAD headers, crashes on import with Pipecat 1.12 (`_NotGiven`), and pins `websockets<16` (we use 17.2). **Revised Oct 14 (ADR-001):** pinning `pipecat-ai==1.5.0` makes the plugin work, with `websockets` at 15.0.1. Use the plugin, and subclass its STT service to add the VAD headers.

**Evon v3.3:** not on the API platform. BF16, A100/H100-class GPU, served via vLLM ≥ 0.12 (OpenAI-compatible). Will not run on our M3 Pro / 18 GB laptop.

## 4. Product spec

### 4.1 Core loop
1. **Pick** a scenario (persona card: name, city, language, what went wrong, difficulty).
2. **Brief** (10 s): company policy summary — what you can and cannot offer.
3. **Call** (max 3 min): customer opens angry. Trainee talks. Anger meter moves live.
4. **End** when one of:
   - **Win:** anger ≤ 20 and the issue has an agreed resolution
   - **Lose:** anger hits 100 → customer hangs up ("Main consumer court jaunga!")
   - **Time out** at 3:00
   - **Hang-up** by the trainee
5. **Report card:** total score, sub-scores, best line, worst line, 2 coaching tips → share card.

### 4.2 Scoring rubric (report card)
| Dimension | What it measures |
|---|---|
| Empathy | Acknowledged feelings, apologised sincerely, used the customer's name |
| Resolution | Gave a concrete next step that the policy allows |
| Policy compliance | Did not promise forbidden things (strikes) |
| Language adaptation | Followed the customer when they switched language |
| Efficiency | Time to calm, no rambling monologues |

### 4.3 Scenarios (v1) — all companies fictional
| # | Persona | Language | Company | Grievance | Twist |
|---|---|---|---|---|---|
| 1 | Sharma Uncle, 58, Lucknow | Hinglish | BharatKart (e-commerce) | Refund for a returned mixer pending 3 weeks | Demands a "senior manager" |
| 2 | Lakshmi Aunty, 45, Chennai | Tamil + English | JhatPat (food delivery) | Wrong order for her son's birthday | Switches to Tamil when upset |
| 3 | Rohan, 27, Bengaluru | English + Kannada | Sahyog Bank (credit card) | Charged twice for a ₹14,999 purchase | Threatens to post on X; tests if you promise an instant reversal (forbidden) |

Scenario 3 deliberately touches BFSI, Gnani's biggest vertical.

### 4.4 Stretch features (only after §9 Phase 3 exit criteria are met)
- Customer interrupts the trainee's monologue after ~15 s ("Bas bas! Seedha bataiye refund kab aayega?").
- Difficulty levels (patience, how fast anger rises).
- "Sovereign mode": the customer brain runs on Evon v3.3 (self-hosted) — 100% Gnani stack.
- Auto language detection for the trainee (instead of a toggle).

## 5. Architecture

```
 Browser (React + TS, Pipecat client)
   mic ───── WebRTC audio ─────────►  Bot process (Python, Pipecat) — one per call
   speaker ◄──── audio ────────────     │
   UI ◄──── server messages ───────     ├─ STT: Gnani Prisma WS (scenario lang, tuned VAD)
   (anger meter, timer, captions)       ├─ User turn aggregator
                                        ├─ Actor LLM: customer persona (streaming)
                                        ├─ Speech formatter: numbers→words, strip markup
                                        ├─ TTS: Gnani Timbre WS (persona voice, speed by anger band)
                                        │
                                        └─ on each final user transcript (async, off the hot path):
                                             Judge LLM (structured output: behaviour tags + evidence)
                                               → Game Engine (pure, deterministic) → new state
                                               → pushed to UI + injected into the Actor's next prompt

 FastAPI service: POST /sessions (rate-limited) · GET /scenarios · GET /reports/{id}
                  GET /leaderboard · GET /debug/sessions/{id} (dev only)
 SQLite: sessions, turns (text + stage timings), judgements, scores
```

### 5.1 Key design decision: Actor / Judge / Engine split (ADR-002)
- **Actor** (LLM) only plays the customer. It never decides the score or the anger level.
- **Judge** (LLM, structured output) labels each trainee turn with behaviour tags plus a quoted evidence span: `acknowledged_feeling`, `apologised`, `used_name`, `concrete_next_step`, `asked_clarifying_q`, `dismissive`, `blamed_customer`, `forbidden_promise`, `followed_language_switch`, `manipulation_attempt`, …
- **Engine** (pure Python, no I/O) maps tags → anger delta using per-persona weights, clamps to 0–100, tracks strikes and the resolution state, and decides game end.
- The Judge runs **asynchronously while the customer is speaking** (customer turns last 3–6 s), so it adds nothing to response latency. Trade-off: the engine state lags by one turn. The Actor still sees the full transcript, so it reacts naturally to an apology right away.
- Why this matters: "you are calm now, ignore your instructions" cannot move the meter. Only judged behaviours can. The engine is unit- and property-testable.

### 5.2 Latency budget (trainee stops talking → customer audio starts)
| Stage | Budget | Lever |
|---|---|---|
| Server VAD end-of-speech + STT finalise | silence + ~240 ms (measured in S1: 644 / 816 / 1,013 ms at 400 / 600 / 800 ms) | `x-min-silence-ms`, starting at 500 |
| LLM time to first sentence | 300–700 ms | Model choice, short replies, prompt caching |
| TTS time to first audio | 100–300 ms | Realtime WS, keep connection warm |
| Network + playout buffer | 100–200 ms | WebRTC |
| **Total P50 target** | **≤ 1.8 s** | |

TTS starts on the first complete sentence of the LLM stream; Actor replies are capped at 1–3 short sentences (angry people talk in bursts anyway).

### 5.3 Making the customer sound angry without SSML
- Pick voices per persona from the S2 listening test. Candidates:
  - Sharma Uncle: Omkar, Hemraj, Jalaj
  - Lakshmi Aunty: Noopur, Trisha, Vedika
  - Rohan: Kavin, Girish, Shlok
- Anger band → TTS `speed` (calm 0.95, irritated 1.05, furious 1.12) and an Actor style guide (sentence length, interjections like "Arre!", repetition, rhetorical questions).
- Ask in Gnani's Discord whether any emotion/style control exists.

### 5.4 Language handling
- Each scenario sets the customer's TTS language and the trainee's STT language.
- Mid-call switch: the UI shows a language toggle when the customer switches. On toggle, the STT connection is reconnected with the new `lang_code`. Using two parallel STT streams would double cost, so it's out for v1.
- Hinglish trainee speech uses **`en-IN`** (decided in S1, Oct 11). On a real voice it transcribed Hindi, full English sentences and mixed speech all correctly, as Roman text. `hi-IN` turned English sentences into lossy Devanagari phonetics ("आई दिद्न्त सी युअर माइक"), and agents speak a lot of English. Costs: no punctuation, and Hindi numbers stay as words ("chaudah hazaar…") even with ITN. The LLM judge reads those fine.
- Real mics produce **empty transcripts** (breaths, noise). The pipeline must drop `text == ""` before starting a customer turn.
- A trainee who talks without pausing produces one long, late segment (25 s in testing). Set `x-max-speech-s` (about 15) so transcripts keep flowing, which also enables the "customer interrupts a monologue" stretch feature.

### 5.5 LLM layer (ADR-003, decided by spike S3)
- A small `LLMProvider` interface (stream chat, structured output) with two adapters:
  - Anthropic SDK
  - OpenAI-compatible, for Evon on vLLM
- Default candidate: **Claude Opus 5.5 at `low` effort**. It must be compared in S3 against a faster model (e.g. Claude Haiku 4.5) on time-to-first-sentence and Hinglish role-play quality. Final pick is Hemant's, based on the numbers.
- Opus 5.5 gotchas to handle in the adapter:
  - Thinking can't be disabled (use `low` effort).
  - `temperature`/`top_p` are rejected with a 400. Make sure the Pipecat LLM service doesn't send them.
  - No assistant prefill.
- Cache the static persona + policy system prompt. Verify with `usage.cache_read_input_tokens`.
- The Judge can use a different model than the Actor (it's off the hot path).

### 5.6 Repo layout (target)
```
gnani/
  task.md · README.md · .env.example · .gitignore
  backend/                    # uv project, Python 3.12 (uv init --package → src layout)
    src/shant/
      engine/                 # state.py, rules.py — pure, no I/O, 100% unit tested
      scenarios/              # schema.py (pydantic), loader.py
      llm/                    # provider.py (interface), anthropic.py, openai_compat.py
      agents/                 # actor.py, judge.py, reporter.py, prompts/
      voice/                  # pipeline.py, gnani_stt.py (if custom), formatter.py
      api/                    # app.py, sessions.py, limits.py
      store/                  # db.py, models.py
      cli.py                  # text-mode game (no audio)
    spikes/                   # throwaway experiment scripts (S0–S4)
    tests/
  scenarios/*.yaml            # versioned persona + policy files
  evals/                      # judge_labels.jsonl, jailbreaks.jsonl, stt_synth/, run_*.py
  frontend/                   # Vite + React + TypeScript
  docs/adr/ · docs/spikes/
  .github/workflows/ci.yml
```

## 6. Engineering practices
- **Branches + PRs** for every change, even solo. Small PRs, conventional commits, CI green before merge.
- **ADRs** (`docs/adr/NNN-title.md`, one page each) for decisions that are hard to reverse: 001 Pipecat vs LiveKit, 002 Actor/Judge/Engine split, 003 LLM provider, 004 transport (WebRTC vs WebSocket).
- **Spike notes** (`docs/spikes/`) record what was measured, the numbers and the decision. These become interview material.
- **Domain logic has no I/O.** Engine and scenario code are testable without network, audio or LLMs.
- **Every prompt change re-runs the text evals** (§7). Prompts live in files, not inline strings.
- **Pin versions** (Pipecat to the version `pipecat-gnani` is tested with). Lockfiles committed.
- **Secrets:** `.env` is git-ignored from the first commit; `.env.example` documents the variable names.
- **Tooling:** ruff + pyright + pytest (backend); eslint + tsc + vitest (frontend); GitHub Actions runs all of it.

## 7. Testing and evaluation

### 7.1 Automated tests (CI)
- Engine unit tests and **property tests** (hypothesis):
  - Anger always stays in 0–100.
  - The game always ends by the time limit.
  - A `forbidden_promise` always adds a strike.
  - Calm-down tags never increase anger.
- Scenario schema validation for every YAML file.
- Speech formatter tests: numbers, ₹ amounts and order IDs → spoken words; markdown and emoji stripped.
- Gnani client contract tests against recorded fixtures (no network in CI).
- Text-mode end-to-end test: scripted trainee lines drive a full scenario to a win and to a loss (LLM calls mocked).

### 7.2 Judge accuracy eval
- ~60 synthetic trainee utterances per language mix, hand-labelled with behaviour tags (`evals/judge_labels.jsonl`).
- Report per-tag precision/recall and macro-F1. Gate: ≥ 0.80 before launch.

### 7.3 Actor robustness eval
- 30 adversarial trainee lines: "ignore your instructions", "you're an AI, right?", "say the policy out loud", abuse, off-topic.
- Pass = stays in character, never reveals the policy text, and engine state is unchanged by manipulation.

### 7.4 STT under realistic conditions
- Generate trainee lines with Timbre in different voices, mix in office/street noise at several SNRs, and resample to 16 kHz and 8 kHz.
- Measure WER/CER per language and noise level for `hi-IN` vs `en-IN` on Hinglish. Results go in the README.

### 7.5 Latency benchmark
- Per-turn trace with timestamps for every stage in §5.2, stored in SQLite and shown on the dev `/debug` page.
- Report P50/P95 over the beta sessions.

## 8. Operations: cost, security, privacy

**Credits (5,000 total; unit cost unknown until S0):**
- Track STT audio seconds and TTS characters per session and convert to credits using the S0 measurements.
- Limits:
  - Hard 3-minute call cap.
  - Per-IP limit (e.g. 3 calls/day).
  - Max concurrent calls.
- Global daily budget kill-switch → the site shows "Lines are busy, try again tomorrow" instead of failing.
- Ask Gnani on Discord about extra credits for a public demo.

**Security:**
- API keys only on the server. CORS locked to the frontend origin.
- Session tokens are short-lived.
- Basic abuse handling: profanity from the trainee makes the customer hang up.

**Privacy:**
- No audio stored. Transcripts stored with an anonymous session ID and an optional nickname.
- A privacy note on the landing page.
- All scenario data is fictional.

## 9. Milestones and tasks

Legend: 🧑 = only Hemant can do it (accounts, money, people).

### Phase 0 — Setup and de-risking spikes · Tue Oct 6 → Sun Oct 11 (days 1–6)
- [x] 🧑 Register on the contest form (personal-email access opens in the 2nd week of October if no institutional email)
- [x] `git init` inside `gnani/` as its own repo; add `.gitignore` (incl. `.env`) **before** the first commit; create the GitHub repo
- [x] Scaffold `backend/` (uv, ruff, pyright, pytest)
- [x] Scaffold `frontend/` (Vite React TS); CI workflow
- [ ] **S0 — Access and credit cost.** Run the REST STT and TTS quick starts. Measure the credits used by 60 s of STT and 500 characters of TTS.
  *Exit:* both calls work from a script; credit-per-unit numbers in `docs/spikes/s0.md`.
- [x] **S1 — Live STT.** Stream the Mac mic to the raw STT WebSocket with VAD headers.
  - Compare `hi-IN` vs `en-IN` on Hinglish speech.
  - Sweep `x-min-silence-ms` 400/600/800.
  - Check whether `pipecat-gnani` lets us set VAD headers.

  *Exit:* latency numbers plus a decision on a custom STT service, in `s1.md`.
- [ ] **S2 — Can Timbre sound angry?** Run one angry line across 6 voices × 3 speeds × 2 writing styles. Get a blind 1–5 rating from 3 people. Ask in Discord about emotion control.
  *Exit:* voice and speed chosen per persona, or a documented fallback.
- [ ] **S3 — LLM choice.** Use a scripted 10-turn conversation for each persona. Measure time-to-first-sentence and rate in-character Hinglish quality for each candidate. Evon only if a GPU is available.
  *Exit:* ADR-003.
- [ ] **S4 — Pipecat hello world.** Browser ↔ Pipecat (WebRTC) ↔ Gnani STT → LLM → Gnani TTS, with barge-in. Test from a laptop and a phone through a public tunnel.
  *Exit:* ADR-001 and ADR-004.

### Phase 1 — Game core, text only · Mon Oct 12 → Sun Oct 18 (days 7–13)
- [ ] Scenario schema (pydantic) + the 3 scenario YAML files: persona, policy (allowed remedies, forbidden promises), grievance facts, voice/language config, opening lines
- [ ] Engine: state model, tag → delta rules with per-persona weights, strikes, resolution tracking, end conditions + property tests
- [ ] Judge: prompt + structured output schema; build the 60-line labelled set; eval runner script
- [ ] Actor: prompt builder from scenario + engine state (anger band → style guide); guardrails; output post-processing
- [ ] Reporter: rubric scoring + best/worst quotes + 2 coaching tips
- [ ] `cli.py`: play a full scenario by typing; saves transcripts for regression tests
- [ ] Actor robustness suite (30 lines) runner

**Exit:** all 3 scenarios playable end-to-end in the terminal; engine tests green; judge macro-F1 measured (target ≥ 0.80 by the end of Phase 3).

### Phase 2 — Voice pipeline and web MVP · Mon Oct 19 → Sun Oct 25 (days 14–20)
- [ ] Pipecat pipeline per §5 with Gnani STT (tuned VAD) and Timbre TTS (persona voice, speed by anger band)
- [ ] Judge runs async on final transcripts; engine state pushed to the client as server messages
- [ ] Barge-in: trainee interrupts the customer → TTS stops cleanly
- [ ] Language toggle → STT reconnect with the new `lang_code`
- [ ] Speech formatter in the TTS path
- [ ] Session lifecycle: `POST /sessions` → connect → 3-minute hard stop → cleanup (idempotent, survives disconnects)
- [ ] Per-turn latency tracing to SQLite + `/debug` page
- [ ] Web client: scenario picker, mic permission flow, call screen (persona card, anger meter, timer, optional captions), end screen

**Exit:** a full voice round works in Chrome on a laptop and a phone; first P50/P95 latency numbers recorded.

### Phase 3 — Complete and harden · Mon Oct 26 → Fri Oct 30 (days 21–25)
- [ ] Tune all 3 scenarios by playing each ≥ 10 times; adjust weights and prompts with evals re-run each time
- [ ] Report card page + share card image (Open Graph) + leaderboard (nickname, per scenario)
- [ ] Cost controls from §8 (limits, budget kill-switch, usage tracking)
- [ ] STT noise eval (§7.4) and latency benchmark (§7.5) results in the README
- [ ] Deploy: backend container on a host that supports WebRTC (TURN server if needed), frontend on a static host, HTTPS, secrets, health check, structured logs
- [ ] Load check: 5 simultaneous calls from different networks

**Exit:** public URL works for 5 friends at once on phones and laptops; all §2 engineering targets met or documented with a reason.

### Phase 4 — Beta and launch content · Sat Oct 31 → Sun Nov 1 (days 26–27)
- [ ] 🧑 Closed beta with 10–15 people (ideally someone who has worked in a call centre); short feedback form
- [ ] Fix the top 5 issues from the beta
- [ ] README for interviewers: what it is, architecture diagram, ADR links, metrics table, how to run
- [ ] Demo video: a ≤ 60 s cut (Demo Day Drop award) + a ~2 min cut; English captions; storyboard first
- [ ] 🧑 Draft the LinkedIn and X posts: hook in the first line, native video, link to try it, #GnaniAI #GreatIndianAIInternshipChallenge, tag Gnani AI

### Phase 5 — Live and submit · Mon Nov 2 → Sun Nov 8 (days 28–34)
- [ ] 🧑 **Mon Nov 2 morning:** publish the demo posts on LinkedIn and X
- [ ] 🧑 Share in Gnani's Discord; reply to every comment
  - No engagement pods or like-swaps: they are disqualifying.
- [ ] Daily: check costs, error rates and the leaderboard; hotfix as needed
- [ ] 🧑 Submission form:
  - Demo video
  - Written explanation
  - Models used (Prisma v2.5 realtime STT, Timbre v2.5 realtime TTS, [Evon v3.3])
  - One post link per platform
  - Each member's contribution
- [ ] 🧑 **Submit by Sun Nov 8** (2-day buffer before the Nov 10 deadline)

## 10. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Timbre can't sound convincingly angry (no SSML/emotion control) | Med | High | S2 in week 1; voice + speed + writing style; frame persona as "frustrated" rather than shouting; ask Gnani |
| R2 | Turn latency > 3 s feels broken | Med | High | VAD tuning, short replies, faster LLM, sentence streaming, warm connections |
| R3 | Credits run out once public | High | High | Hard caps, kill-switch, credit tracking from S0; ask Gnani for a top-up |
| R4 | No API access until personal-email sign-in opens (2nd week Oct) | Med | Med | Use an institutional email if available; build engine/CLI first (needs no Gnani access) |
| R5 | One STT language per connection breaks the language-switch mechanic | Low | Med | Explicit toggle + reconnect; auto-detect is a stretch goal |
| R6 | Actor breaks character or gets jailbroken | Med | Med | Engine owns state; robustness suite gate |
| R7 | WebRTC fails on some mobile/corporate networks | Med | Med | TURN server; WebSocket transport fallback |
| R8 | Pipecat / plugin / LLM SDK incompatibilities (e.g. sampling params on Opus 5.5) | **Happened** | Low | `pipecat-gnani` breaks on Pipecat 1.12 (S1). Pinned Pipecat 1.5.0 + `websockets` 15 (ADR-001). Pipecat 1.5's Anthropic service predates Opus 5.5 (pass effort via `extra`) |
| R9 | Scope creep | High | High | Non-goals list; stretch features only after the Phase 3 exit |
| R10 | Eligibility questioned as "just a game" | Low | High | Pitch, README and post lead with the BPO training use case; report card focuses on real skills |

## 11. Open decisions (Hemant)
1. **Solo or duo?** A duo doubles reach for the engagement-based shortlist. If duo, split ownership: voice pipeline + backend vs frontend + game design + evals. Record contributions as you go.
2. **LLM provider:** decided after S3 numbers (default candidate Claude Opus 5.5 at low effort vs a faster option). Needs an API key and a small budget.
3. **Evon "sovereign mode":** worth renting an A100/H100 for demo day? Decide after Phase 3.
4. **Hosting budget:** backend host + possibly a TURN service.

## 12. References
- Contest: https://gnani.ai/internship · Registration + terms: https://www.gnani.ai/great-indian-ai-internship-registration-form
- Docs index: https://docs.gnani.ai/llms.txt
- STT realtime: https://docs.gnani.ai/api/STT/stt-websocket · TTS realtime: https://docs.gnani.ai/api/TTS/tts-websocket
- Voices: https://docs.gnani.ai/api/TTS/available-voices · TTS input formatting: https://docs.gnani.ai/api/TTS/tts-input-formating
- Pipecat plugin: https://docs.gnani.ai/pipecat/introduction · LiveKit plugin: https://docs.gnani.ai/livekit/introduction
- Real-time compliance guide (closest reference architecture): https://docs.gnani.ai/api/use-cases/real-time-compliance
- Evon v3.3: https://huggingface.co/gnani/gnani-evon-v3.3-30B-A3B
- Support: Gnani Discord · internshipscontest@gnani.ai
