"""S0: send the TTS clips back through Prisma STT over REST."""

import time
import wave
from pathlib import Path

from dotenv import load_dotenv
from gnani.stt import GnaniSTTClient
from gnani.stt.exceptions import APIError

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "backend" / "out"
load_dotenv(ROOT / ".env")

client = GnaniSTTClient()


def transcribe(clip: Path, lang: str) -> str:
    for attempt in range(5):
        try:
            return client.transcribe(clip, language_code=lang)["transcript"]
        except APIError as error:
            if error.status_code != 429:
                raise
            wait = 2**attempt
            print(f"   rate limited, retrying in {wait} s")
            time.sleep(wait)
    raise RuntimeError(f"still rate limited after 5 attempts: {clip.name} [{lang}]")


for clip in sorted(OUT.glob("*.wav")):
    with wave.open(str(clip)) as w:
        bytes_per_second = w.getframerate() * w.getsampwidth() * w.getnchannels()
    # Gnani's WAV header declares an unknown length (0xFFFFFFFF), so measure the file instead.
    seconds = (clip.stat().st_size - 44) / bytes_per_second
    for lang in ("hi-IN", "en-IN"):
        print(f"{clip.name} ({seconds:.1f} s) [{lang}] {transcribe(clip, lang)}")
