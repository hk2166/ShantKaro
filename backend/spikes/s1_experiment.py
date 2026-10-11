"""S1 experiment: measure Gnani realtime STT on synthetic Hinglish call-centre speech.

Generates ten agent lines with Timbre (cached in out/s1/), joins them with pauses into one
stream, and sends it through realtime STT at real-time pace for each setting. For each
setting it reports the delay from the end of each sentence to its last transcript, and how
many sentences came back split into several transcripts.

Run from backend/:
  uv run python spikes/s1_experiment.py hi-IN:600 en-IN:600
"""

import asyncio
import json
import statistics
import sys
import time
from array import array
from pathlib import Path

from gnani.tts import AudioConfig, GnaniTTSClient
from gnani.tts.exceptions import APIError
from s1_live_stt import ROOT, SAMPLE_RATE, load_pcm, paced_frames, transcribe_stream

OUT = ROOT / "backend" / "out" / "s1"
# Longer than silence + latency, so each sentence's transcript lands before the next one ends.
PAUSE_SECONDS = 2.5
SILENCE_LEVEL = 300

SENTENCES = [
    ("Deepak", "सर, मैं आपकी problem समझ सकता हूँ, मैं अभी आपके refund का status check करता हूँ।"),
    ("Chitra", "आपका order ID बता दीजिए please, मैं system में देख लेती हूँ।"),
    ("Vikrant", "I'm really sorry for the delay, आपका refund अड़तालीस घंटे में process हो जाएगा।"),
    ("Bhavna", "मैम, मैं इसे अभी senior team को escalate कर रही हूँ।"),
    ("Deepak", "आपके card पर चौदह हज़ार नौ सौ निन्यानवे रुपये दो बार charge हुए हैं, right?"),
    ("Chitra", "आपकी frustration बिल्कुल जायज़ है, ये हमारी गलती है।"),
    ("Vikrant", "मैं आपको एक reference number दे रहा हूँ, please इसे note कर लीजिए।"),
    ("Bhavna", "क्या आप अपना registered email confirm कर सकती हैं?"),
    ("Deepak", "आपका replacement कल शाम तक deliver हो जाएगा, मैं personally track करूँगा।"),
    ("Chitra", "क्या मैं आपकी और किसी चीज़ में help कर सकती हूँ?"),
]


def synthesize(client: GnaniTTSClient, voice: str, text: str, path: Path) -> None:
    for attempt in range(5):
        try:
            client.synthesize(
                text,
                voice=voice,
                model="timbre-v2.5",
                language="hi-IN",
                audio_config=AudioConfig(sample_rate=SAMPLE_RATE),
                output_file=path,
            )
            return
        except APIError as error:
            if error.status_code != 429:
                raise
            time.sleep(2**attempt)
    raise RuntimeError(f"still rate limited after 5 attempts: {path.name}")


def trim_silence(pcm: bytes) -> bytes:
    """Cut the quiet lead-in and tail Timbre adds, so 'end of clip' means 'end of speech'."""
    samples = array("h", pcm)
    loud = [i for i, sample in enumerate(samples) if abs(sample) > SILENCE_LEVEL]
    return samples[loud[0] : loud[-1] + 1].tobytes() if loud else pcm


def load_sentences() -> list[bytes]:
    OUT.mkdir(parents=True, exist_ok=True)
    client = GnaniTTSClient()
    clips = []
    for index, (voice, text) in enumerate(SENTENCES):
        path = OUT / f"sentence_{index:02d}.wav"
        if not path.exists():
            synthesize(client, voice, text, path)
        clips.append(trim_silence(load_pcm(path)))
    return clips


def build_stream(clips: list[bytes]) -> tuple[bytes, list[tuple[float, float]]]:
    """Join clips with silent pauses. Returns the audio and each sentence's (start, end) in s."""
    pause = bytes(int(PAUSE_SECONDS * SAMPLE_RATE) * 2)
    audio = bytearray(pause)
    spans = []
    for clip in clips:
        start = len(audio) / 2 / SAMPLE_RATE
        audio += clip
        spans.append((start, len(audio) / 2 / SAMPLE_RATE))
        audio += pause
    return bytes(audio), spans


async def run_setting(
    audio: bytes, spans: list[tuple[float, float]], lang: str, silence_ms: int
) -> dict:
    started, transcripts = await transcribe_stream(
        paced_frames(audio), lang, silence_ms, on_transcript=lambda _: None
    )
    rows = []
    for index, (start, end) in enumerate(spans):
        window_end = spans[index + 1][0] if index + 1 < len(spans) else float("inf")
        mine = [t for t in transcripts if start <= t.received_at - started < window_end]
        rows.append(
            {
                "reference": SENTENCES[index][1],
                "transcripts": [t.text for t in mine],
                "delay_ms": round((mine[-1].received_at - started - end) * 1000) if mine else None,
                "server_latency_ms": [t.server_latency_ms for t in mine],
            }
        )
    delays = [row["delay_ms"] for row in rows if row["delay_ms"] is not None]
    return {
        "lang": lang,
        "silence_ms": silence_ms,
        "median_delay_ms": statistics.median(delays) if delays else None,
        "max_delay_ms": max(delays) if delays else None,
        "split_sentences": sum(len(row["transcripts"]) > 1 for row in rows),
        "missing_sentences": sum(not row["transcripts"] for row in rows),
        "rows": rows,
    }


def print_result(result: dict) -> None:
    print(f"\n=== {result['lang']}, silence {result['silence_ms']} ms ===")
    for index, row in enumerate(result["rows"]):
        texts = " | ".join(row["transcripts"]) or "(nothing)"
        print(f"{index:2d}. {row['delay_ms']} ms  {texts}")
    print(
        f"median delay {result['median_delay_ms']} ms, max {result['max_delay_ms']} ms, "
        f"split {result['split_sentences']}/10, missing {result['missing_sentences']}/10"
    )


def main() -> None:
    settings = [(lang, int(ms)) for lang, ms in (arg.split(":") for arg in sys.argv[1:])]
    clips = load_sentences()
    audio, spans = build_stream(clips)
    print(f"{len(clips)} sentences, {len(audio) / 2 / SAMPLE_RATE:.0f} s of audio per setting")
    for lang, silence_ms in settings or [("hi-IN", 600), ("en-IN", 600)]:
        result = asyncio.run(run_setting(audio, spans, lang, silence_ms))
        print_result(result)
        path = OUT / f"result_{lang}_{silence_ms}.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        time.sleep(2)


if __name__ == "__main__":
    main()
