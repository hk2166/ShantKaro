# Shant Karo — Day-by-Day Plan

Repo root: `~/Desktop/personal/gnani`. Every path below is relative to it.
Specs and reasoning are in [task.md](task.md); references like §5.1 point there.

**How to use this**
- Do one day at a time and tick the boxes as you go.
- Work on a branch (`day03-live-stt`), open a PR to `main`, and merge when CI is green.
- Write every number you measure into `docs/spikes/` or the README. Those numbers are your interview material.
- If a day slips, use the next 🛟 buffer day. Don't shift the whole plan.
- Time assumed: ~3–4 h on weekdays, ~6 h on weekends.
- 🧑 marks something only you can do (accounts, people, posting).

**Progress (Oct 16):** Days 1–5 and 7–11 done, plus Day 12's two scenario files. Day 6: ADRs done, voice tests pending. Back on schedule. Open for you: play the terminal game yourself, S2 ratings, talking to the echo bot (laptop + phone), Discord questions, STT cost on the dashboard. Next: Day 12 (report card).

**Blocked on Gnani API access?** Sign-in with a personal email opens in the 2nd week of October. Until then, do Days 7–10 first (they need no Gnani access) and come back to Days 2–6.

| Week | Dates | By the end of the week |
|---|---|---|
| 1 | Oct 6 – Oct 11 | Repo set up, 5 spikes done, biggest risks answered |
| 2 | Oct 12 – Oct 18 | Whole game playable by typing in the terminal |
| 3 | Oct 19 – Oct 25 | Whole game playable by voice in your own web page |
| 4 | Oct 26 – Nov 1 | Deployed, beta-tested, demo video ready |
| 5 | Nov 2 – Nov 8 | Posted, running live, submitted |

---

## Week 1 — Setup and spikes

### Day 1 · Tue Oct 6 (tonight, ~1 h) · Repo setup
- [x] 🧑 Register on the contest form if you haven't: https://www.gnani.ai/great-indian-ai-internship-registration-form
- [x] Make `gnani` its own git repo and ignore secrets **before** the first commit:
  ```bash
  cd ~/Desktop/personal/gnani
  git init -b main
  cat > .gitignore <<'EOF'
  .env
  .venv/
  __pycache__/
  node_modules/
  dist/
  out/
  .DS_Store
  *.wav
  *.pcm
  EOF
  printf "GNANI_API_KEY=\nANTHROPIC_API_KEY=\n" > .env.example
  git status    # .env must NOT appear in this list
  ```
- [x] Scaffold the backend and folders:
  ```bash
  uv init --package --name shant --python 3.12 backend
  cd backend && uv add --dev ruff pyright pytest hypothesis && cd ..
  mkdir -p backend/tests backend/spikes docs/adr docs/spikes scenarios evals
  ```
- [x] Add `backend/tests/test_smoke.py` containing `def test_smoke(): assert True` and run `cd backend && uv run pytest`
- [x] First commit; create a **private** GitHub repo; push (`hk2166/ShantKaro`)

**Done when:** `uv run pytest` passes, `.env` is not tracked, and the code is on GitHub.

### Day 2 · Wed Oct 7 · First Gnani calls (spike S0) + frontend scaffold
- [x] 🧑 Create an API key at https://app.gnani.ai/voice and put it in `.env`
- [x] `cd backend && uv add gnani-vachana python-dotenv websockets`
- [x] `backend/spikes/s0_tts.py`: Timbre REST → `out/hello.wav` with a Hinglish line (voice `Poorvi`, language `hi-en`)
- [x] `backend/spikes/s0_stt.py`: send that WAV to STT REST and print the transcript (a full round trip)
- [ ] Measure credits: note the dashboard balance before and after ~60 s of STT and ~500 characters of TTS → `docs/spikes/s0.md`
- [x] Frontend scaffold: `npm create vite@latest frontend -- --template react-ts`
- [x] CI: `.github/workflows/ci.yml` running ruff, pyright and pytest (backend), plus tsc and build (frontend)

**Done when:** you hear your Hinglish clip, get its transcript back, and CI is green.

### Day 3 · Thu Oct 8 · Live speech-to-text from your mic (spike S1)
- [x] `cd backend && uv add --dev sounddevice` (numpy turned out not to be needed)
- [x] `backend/spikes/s1_live_stt.py`: stream the mic to `wss://api.vachana.ai/stt/v3/stream` with headers (§3) and print each `transcript` and its `latency`
  - Hint: `sounddevice.RawInputStream(samplerate=16000, channels=1, dtype="int16", blocksize=512)` gives exactly 1,024-byte blocks every 32 ms, which is what Gnani requires.
  - If 16 kHz fails on your Mac, record at 48 kHz and send `x-sample-rate: 48000`.
- [x] Say the same 10 Hinglish sentences with `lang_code` `hi-IN` and with `en-IN`. Which output is cleaner? (done with Timbre-generated speech via `s1_experiment.py`: `hi-IN` wins)
- [x] Try `x-min-silence-ms` at 400, 600 and 800. How fast is it, and how often does a sentence get split?
- [x] Read the `pipecat-gnani` source: can `GnaniSTTService` pass VAD headers? If not, you'll write a small custom STT service on Day 14.
- [x] Write `docs/spikes/s1.md`: numbers + decisions (private, git-ignored)

**Done when:** you see your own speech transcribed live, and you've picked a language code and a silence value.

### Day 4 · Fri Oct 9 · Can Timbre sound angry? (spike S2) + LLM timing script
- [x] `backend/spikes/s2_anger.py`: generate one angry line per persona, each in 3 voices at speeds 1.0, 1.08 and 1.15 (27 clips). Use random file names plus a hidden answer key.
  - Sharma Uncle: Omkar, Hemraj, Jalaj
  - Lakshmi Aunty: Noopur, Trisha, Vedika
  - Rohan: Kavin, Girish, Shlok
- [ ] 🧑 Send the clips to 3 friends to rate 1–5 for "sounds like a genuinely annoyed customer"
- [ ] 🧑 Ask in the Gnani Discord whether Timbre v2.5 has any emotion, style or SSML control
- [x] 🧑 Get an LLM API key (decision §11.2)
- [x] `backend/spikes/s3_llm.py`: stream one reply and print time to first token and time to first full sentence

**Done when:** clips are with your raters, and the timing script works for one model.

### Day 5 · Sat Oct 10 · Pick the LLM (spike S3) + start Pipecat (spike S4)
- [x] Write a 10-turn scripted conversation for each persona (`backend/spikes/s3_scripts/`)
- [x] Run each candidate model on all three scripts:
  - Candidates: the default Claude Opus 5.5 at `low` effort vs a faster one, e.g. Claude Haiku 4.5.
  - Record the P50 time to first sentence.
  - Rate the replies 1–5 for "in character, natural code-mixing, short".
- [x] Write `docs/adr/003-llm-provider.md`: which model and why (§5.5 lists the gotchas)
- [x] Install Pipecat pinned to the version `pipecat-gnani` is tested with (v1.5.0), plus `pipecat-gnani`
- [x] Run the plugin's foundational example locally (as `spikes/s4_echo_bot.py`: same structure, but it echoes instead of calling an LLM, since there's no key yet)

**Done when:** ADR-003 is written and the Pipecat example runs.

### Day 6 · Sun Oct 11 · Talk to a bot in your browser (spike S4) + week 1 wrap-up
- [ ] Wire up browser ↔ Pipecat (WebRTC) ↔ Gnani STT → your LLM → Gnani TTS, with a one-line "angry customer" prompt
- [ ] Barge-in: talk over the bot; it should stop speaking
- [ ] Open it on your phone through a tunnel (e.g. cloudflared). Does WebRTC connect?
- [ ] Collect the S2 ratings → choose a voice and speeds per persona → `docs/spikes/s2.md`
- [x] Write `docs/adr/001-pipecat-vs-livekit.md` and `docs/adr/004-transport.md`
- [ ] Optional: build-in-public post #1 ("building a voice trainer for call-centre agents on Gnani AI")

**Done when:** you've had a spoken conversation with your bot on your laptop and your phone.

---

## Week 2 — The game, text only (no audio)

All code goes in `backend/src/shant/`.

### Day 7 · Mon Oct 12 · Scenario files
- [x] `scenarios/schema.py`: pydantic models with these fields:
  - persona
  - policy (allowed remedies, forbidden promises)
  - grievance facts
  - voice config (voice, TTS and STT language, speed per anger band)
  - opening lines
  - tag weights
- [x] `scenarios/sharma_uncle.yaml`: fictional company BharatKart, Hinglish, refund pending 3 weeks
- [x] `scenarios/loader.py` + tests: every YAML in `scenarios/` validates, and a broken file fails with a clear error

**Done when:** tests load and validate scenario 1.

### Day 8 · Tue Oct 13 · Game engine
- [x] `engine/state.py`: `GameState` (anger 0–100, strikes, resolution, turn count, elapsed time, status)
- [x] `engine/rules.py`: a pure function `apply(state, judgement, scenario) -> GameState`, plus the end conditions from §4.1
- [x] Unit tests for each rule + hypothesis property tests (§7.1)

**Done when:** `engine/` has full test coverage and imports nothing that does I/O.

### Day 9 · Wed Oct 14 · LLM layer + the customer (Actor)
- [x] `llm/provider.py`: a small interface (stream text, structured output) + the adapter you chose in ADR-003 (`llm/claude.py`; structured output comes with the Judge on Day 10)
- [x] `agents/actor.py`: build the customer prompt from the scenario and the anger band, using the style guide in §5.3. Prompts live in `agents/prompts/*.md`.
- [x] `voice/formatter.py`: strip markdown, stage directions, emoji and wrapping quotes. Add tests. (Numbers to words isn't needed: Gnani's TTS normalises numbers, ₹ and IDs itself.)

**Done when:** a quick script prints an in-character reply at anger 30 and at anger 90, and they sound clearly different.

### Day 10 · Thu Oct 15 · The Judge
- [x] `agents/judge.py`: structured output of behaviour tags + an evidence quote (tag list in §5.1)
- [x] Write 60 labelled trainee lines → `evals/judge_labels.jsonl`, mixing Hinglish, English, Tamil-English and Kannada-English
- [x] `evals/run_judge.py`: per-tag precision/recall + macro-F1 (Opus 5.5 medium: **1.00**, P50 2.8 s / P95 5.1 s; Sonnet 5.5: 0.96)

**Done when:** your first judge F1 number is written down. The target is ≥ 0.80 by Day 24.

### Day 11 · Fri Oct 16 · Play it in the terminal
- [x] `cli.py` (`uv run shant <scenario>`, built on `game/call.py`): you type as the agent → the Actor replies → the Judge labels your line → the Engine updates → the anger meter prints
- [x] Play scenario 1 to a win and to a loss; save the transcripts in `evals/transcripts/` (two scripted games; play your own too)
- [x] Add an end-to-end test that replays a saved transcript with the LLM calls mocked

**Done when:** you can win and lose against Sharma Uncle in the terminal.

### Day 12 · Sat Oct 17 · Other scenarios + report card
- [x] `scenarios/lakshmi_aunty.yaml` (done early, on Day 7): JhatPat food delivery, Tamil + English, switches to Tamil when upset
- [x] `scenarios/rohan.yaml` (done early, on Day 7): Sahyog Bank double charge of ₹14,999; promising an instant reversal is forbidden
- [ ] `agents/reporter.py`: rubric scores (§4.2), best and worst line, 2 coaching tips
- [ ] Play scenarios 2 and 3 in the CLI

**Done when:** all 3 scenarios are playable in the terminal and end with a report card.

### Day 13 · Sun Oct 18 · 🛟 Buffer + robustness
- [ ] `evals/jailbreaks.jsonl` (30 lines, §7.3) + `evals/run_robustness.py`
- [ ] Fix the worst Judge and Actor failures, then re-run both evals
- [ ] Write `docs/adr/002-actor-judge-engine.md`
- [ ] Optional: build-in-public post #2 (a short screen recording of the terminal game)

**Done when:** both evals run and their numbers are recorded.

---

## Week 3 — Voice and the web app

### Day 14 · Mon Oct 19 · Voice pipeline
- [ ] `voice/pipeline.py`: transport → Gnani STT → turn aggregator → Actor (streaming) → formatter → Gnani TTS (persona voice)
  - Use a custom STT service with VAD headers if S1 showed you need one.
- [ ] Run scenario 1 by voice using Pipecat's built-in dev client

**Done when:** Sharma Uncle answers you out loud.

### Day 15 · Tue Oct 20 · Judge and engine in the live call
- [ ] On each final transcript, run the Judge asynchronously → Engine → send the new state to the client as a server message
- [ ] Anger band sets the TTS speed and the Actor's style from the next turn on
- [ ] Endings: customer hang-up line, win line, and a 3-minute timeout that closes the call

**Done when:** the anger level changes during a voice call and the call ends by itself.

### Day 16 · Wed Oct 21 · Sessions, barge-in, language switch
- [ ] FastAPI `POST /sessions` starts one bot per call; hard stop at 3 minutes; cleanup even if the browser disconnects
- [ ] Check that barge-in works with the interruptible TTS service
- [ ] Language toggle message → reconnect STT with the new `lang_code`

**Done when:** 10 calls in a row start and stop cleanly with no leftover bot processes.

### Day 17 · Thu Oct 22 · Measure and cut latency
- [ ] Record a timestamp for every stage in §5.2 on every turn → SQLite (`store/`)
- [ ] `GET /debug/sessions/{id}`: a simple per-turn timing table
- [ ] Tune `x-min-silence-ms`, reply length and sentence streaming; record P50/P95

**Done when:** you know your P50/P95 and which stage is slowest.

### Day 18 · Fri Oct 23 · Web app, part 1
- [ ] Scenario picker with persona cards from `GET /scenarios`
- [ ] Mic permission flow, including the "permission denied" state
- [ ] Connect to the bot with the Pipecat client SDK

**Done when:** you can start a call from your own page.

### Day 19 · Sat Oct 24 · Web app, part 2
- [ ] Call screen: persona card, live anger meter, 3:00 timer, captions toggle, language toggle, hang-up button
- [ ] End screen: result + report card
- [ ] Check the layout at phone width (375 px)

**Done when:** you can play a full round in your UI on laptop and phone.

### Day 20 · Sun Oct 25 · 🛟 Buffer + week 3 wrap-up
- [ ] Play all 3 scenarios by voice and fix what's broken
- [ ] Optional: build-in-public post #3 (a 15-second voice clip of Sharma Uncle)

**Done when:** the Phase 2 exit criteria in task.md §9 are met.

---

## Week 4 — Finish, deploy, beta, video

### Day 21 · Mon Oct 26 · Report card, share card, leaderboard
- [ ] `GET /reports/{id}` + a report page
- [ ] Share card image (Open Graph) showing the score and the best line
- [ ] Leaderboard (nickname only, per scenario)

**Done when:** sharing a report link shows a preview card.

### Day 22 · Tue Oct 27 · Cost and abuse controls
- [ ] Track STT seconds and TTS characters per session → convert to credits using the S0 rates
- [ ] Add these limits:
  - Per-IP daily limit
  - Max concurrent calls
  - Daily budget kill-switch that shows a "Lines are busy, try again tomorrow" screen
- [ ] Profanity from the trainee → the customer hangs up

**Done when:** the kill-switch is tested by setting a tiny budget.

### Day 23 · Wed Oct 28 · Deploy
- [ ] Backend container on a host that supports WebRTC (add a TURN server if phones can't connect)
- [ ] Frontend on a static host with HTTPS
- [ ] Secrets in the host's environment, a health check endpoint, structured logs
- [ ] 🧑 Ask Gnani on Discord about extra credits for a public demo

**Done when:** the public URL works from your phone on mobile data.

### Day 24 · Thu Oct 29 · Tune + evals
- [ ] Play each scenario at least 10 times; adjust weights and prompts; re-run the judge and robustness evals after every change
- [ ] STT noise eval (§7.4): script + results table

**Done when:** judge F1 ≥ 0.80 and 0 of 30 character breaks, or you've written down why not.

### Day 25 · Fri Oct 30 · Load test, beta, README
- [ ] 🧑 Get 5 friends to call at the same time from different networks
- [ ] 🧑 Send the beta link + a short feedback form to 10–15 people
- [ ] Write the README for interviewers: what and why, architecture diagram, ADR links, metrics table, how to run

**Done when:** beta invites are out and the README is complete.

### Day 26 · Sat Oct 31 · Beta fixes
- [ ] Sort the feedback and fix the top 5 issues
- [ ] **Feature freeze.** Bug fixes only from here.

**Done when:** the top 5 issues are fixed and deployed.

### Day 27 · Sun Nov 1 · Demo video + posts
- [ ] Storyboard → record → edit a ≤ 60 s cut and a ~2 min cut, both with English captions
- [ ] 🧑 Draft the LinkedIn and X posts:
  - Hook in the first line
  - Native video
  - Try-it link
  - Hashtags #GnaniAI and #GreatIndianAIInternshipChallenge
  - Tag Gnani AI
- [ ] Make the GitHub repo public after checking the history for secrets: `git log -p | grep -n "API_KEY="` should only show empty values

**Done when:** the video is exported and both posts are drafted.

---

## Week 5 — Launch and submit

### Day 28 · Mon Nov 2 · 🚀 Launch
- [ ] 🧑 Around 9:30 AM IST, publish on LinkedIn and X
- [ ] 🧑 Share in the Gnani Discord and reply to every comment through the day
  - No engagement pods or like-swaps: they can get you disqualified.
- [ ] Watch costs and error logs

### Day 29 · Tue Nov 3 · Live ops
- [ ] Hotfix anything broken, reply to comments, check costs

### Day 30 · Wed Nov 4 · Live ops + optional stretch
- [ ] Only if everything is green: add one stretch feature, e.g. the customer interrupts a long monologue (§4.4)

### Day 31 · Thu Nov 5 · Submission draft + interview prep
- [ ] Write the project explanation: problem, users, models used, architecture, metrics, each member's contribution
- [ ] Rehearse a 5-minute architecture walkthrough using the README and ADRs

### Day 32 · Fri Nov 6 · Refresh the numbers
- [ ] Update the README metrics with real usage: calls played, latency P50/P95, judge F1

### Day 33 · Sat Nov 7 · Fill in the form (don't submit yet)
- [ ] 🧑 Fill in the submission form:
  - Demo video
  - Explanation
  - Models used (Prisma v2.5 realtime STT, Timbre v2.5 realtime TTS, plus Evon v3.3 if used)
  - One post link per platform
- [ ] Confirm both posts are still live and public

### Day 34 · Sun Nov 8 · ✅ Submit
- [ ] 🧑 Submit; keep the confirmation email or a screenshot

**Nov 9–10:** buffer only. Keep the app running and make no risky changes. The deadline is 11:59 PM IST on Tue Nov 10.
