"""S2: can Timbre sound like an angry customer?

Run from backend/:
  uv run python spikes/s2_anger.py generate                    # 27 blind clips for raters
  uv run python spikes/s2_anger.py score out/s2/rater_*.csv    # average returned ratings

Generates one angry line per persona, each in 3 voices at 3 speeds, under shuffled file
names so raters can't tell which voice or speed they're hearing. The answer key stays in
out/s2/answer_key.json; only out/s2/s2_clips_for_raters.zip goes to the raters.
"""

import csv
import json
import random
import statistics
import sys
import time
import zipfile
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from gnani.tts import AudioConfig, GnaniTTSClient
from gnani.tts.exceptions import APIError

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "backend" / "out" / "s2"
CLIPS = OUT / "clips"
KEY = OUT / "answer_key.json"
load_dotenv(ROOT / ".env")

SPEEDS = (1.0, 1.08, 1.15)
SHUFFLE_SEED = 7

PERSONAS = {
    "Sharma Uncle": {
        "language": "hi-IN",
        "voices": ("Omkar", "Hemraj", "Jalaj"),
        "line": "तीन हफ्ते हो गए! तीन हफ्ते! मेरा refund अभी तक नहीं आया, और हर बार आप लोग "
        "बोलते हो process में है। ये कैसी service है? मुझे अभी senior manager से बात करनी है!",
    },
    "Lakshmi Aunty": {
        "language": "ta-IN",
        "voices": ("Noopur", "Trisha", "Vedika"),
        "line": "என் பையனோட பிறந்தநாளுக்கு order பண்ணேன், நீங்க முழுக்க wrong order "
        "அனுப்பியிருக்கீங்க! இப்போ நான் என்ன பண்றது? உடனே இதை சரி பண்ணுங்க!",
    },
    "Rohan": {
        "language": "en-IN",
        "voices": ("Girish", "Shlok", "Kavin"),
        "line": "This is ridiculous! You charged my card twice, fourteen thousand nine hundred "
        "and ninety-nine rupees, twice! I've been on hold for forty minutes. Reverse it "
        "today, or I'm posting this on X.",
    },
}

RATER_INSTRUCTIONS = """Thanks for helping!

Play each clip and rate it 1-5 in the "rating" column of rating_sheet.csv:
how much does it sound like a genuinely annoyed customer on a support call?

  1 = robotic or calm      3 = somewhat annoyed      5 = convincingly angry and real

Rate each clip on its own, don't compare against the others. Send the sheet back when done.
"""


def synthesize(
    client: GnaniTTSClient, text: str, voice: str, language: str, speed: float, path: Path
) -> None:
    for attempt in range(5):
        try:
            client.synthesize(
                text,
                voice=voice,
                model="timbre-v2.5",
                language=language,
                speed=speed,
                # MP3 at 24 kHz returns HTTP 500 once the audio is a few seconds long; 16 kHz works.
                audio_config=AudioConfig(sample_rate=16000, container="mp3", bitrate="128k"),
                output_file=path,
            )
            return
        except APIError as error:
            if error.status_code != 429:
                raise
            time.sleep(2**attempt)
    raise RuntimeError(f"still rate limited after 5 attempts: {path.name}")


def generate() -> None:
    combos = [
        {"persona": persona, "voice": voice, "speed": speed}
        for persona, spec in PERSONAS.items()
        for voice in spec["voices"]
        for speed in SPEEDS
    ]
    random.Random(SHUFFLE_SEED).shuffle(combos)
    key = {f"clip_{index:02d}.mp3": combo for index, combo in enumerate(combos, start=1)}

    CLIPS.mkdir(parents=True, exist_ok=True)
    client = GnaniTTSClient()
    characters = 0
    for name, combo in key.items():
        path = CLIPS / name
        spec = PERSONAS[combo["persona"]]
        if not path.exists():
            synthesize(client, spec["line"], combo["voice"], spec["language"], combo["speed"], path)
            characters += len(spec["line"])
            time.sleep(1)
        print(f"{name}: done")
    KEY.write_text(json.dumps(key, ensure_ascii=False, indent=2))

    sheet = OUT / "rating_sheet.csv"
    with sheet.open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["clip", "customer", "rating", "notes"])
        for name, combo in key.items():
            writer.writerow([name, combo["persona"], "", ""])

    bundle = OUT / "s2_clips_for_raters.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        for name in key:
            archive.write(CLIPS / name, f"clips/{name}")
        archive.write(sheet, "rating_sheet.csv")
        archive.writestr("README.txt", RATER_INSTRUCTIONS)

    print(
        f"\n{len(key)} clips, {characters} new TTS characters "
        f"(about ₹{characters * 2.75 / 1000:.2f})"
    )
    print(f"Send this to raters: {bundle}")
    print(f"Keep this to yourself: {KEY}")


def score(sheets: list[Path]) -> None:
    key = json.loads(KEY.read_text())
    ratings: dict[str, list[float]] = defaultdict(list)
    for sheet in sheets:
        with sheet.open(newline="") as file:
            for row in csv.DictReader(file):
                if row["rating"].strip():
                    ratings[row["clip"]].append(float(row["rating"]))

    by_voice: dict[tuple[str, str], list[float]] = defaultdict(list)
    by_speed: dict[tuple[str, float], list[float]] = defaultdict(list)
    for clip, values in ratings.items():
        combo = key[clip]
        by_voice[(combo["persona"], combo["voice"])].extend(values)
        by_speed[(combo["persona"], combo["speed"])].extend(values)

    print(f"{len(sheets)} sheets, {sum(map(len, ratings.values()))} ratings\n")
    for persona in PERSONAS:
        print(persona)
        voices = sorted(
            ((statistics.mean(v), voice) for (p, voice), v in by_voice.items() if p == persona),
            reverse=True,
        )
        for mean, voice in voices:
            print(f"  voice {voice:8s} {mean:.2f}")
        for speed in SPEEDS:
            values = by_speed.get((persona, speed))
            if values:
                print(f"  speed {speed:<8} {statistics.mean(values):.2f}")
        print()


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "generate":
        generate()
    elif command == "score" and len(sys.argv) > 2:
        score([Path(arg) for arg in sys.argv[2:]])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
