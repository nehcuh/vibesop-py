"""Synthesize narration per sentence, assemble per-scene WAVs, emit timings + SRT.

Run: uv run --no-project --with edge-tts --with pyyaml python scripts/video/tts.py
Falls back to macOS `say -v Tingting` if edge-tts fails (e.g. offline).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import wave
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
OUT = REPO / "dist" / "video"
CACHE = OUT / "tts_cache"
AUDIO = OUT / "audio"
RATE = 24000
LEAD = 0.35  # silence before first sentence of each scene

# Spoken-form substitutions (subtitles keep the original text).
SPOKEN = {
    "VibeSOP": "Vibe SOP",
    "SKILL.md": "skill 点 MD",
    "PROJECT_CONTEXT": "project context",
    "session-end": "session end",
    "scan-candidates": "scan candidates",
    "launchd": "launch D",
    "uv ": "U V ",
    "Pi、": "派、",
}


def spoken(text: str) -> str:
    for k, v in SPOKEN.items():
        text = text.replace(k, v)
    return text


async def synth_edge(text: str, voice: str, rate: str, mp3: Path) -> None:
    import edge_tts

    await edge_tts.Communicate(text, voice, rate=rate).save(str(mp3))


def synth(text: str, voice: str, rate: str) -> Path:
    key = hashlib.sha1(f"{voice}|{rate}|{text}".encode()).hexdigest()[:16]
    wav = CACHE / f"{key}.wav"
    if wav.exists():
        return wav
    src = CACHE / f"{key}.mp3"
    try:
        asyncio.run(synth_edge(text, voice, rate, src))
    except Exception as e:  # offline fallback
        print(f"  edge-tts failed ({e}); falling back to say")
        src = CACHE / f"{key}.aiff"
        subprocess.run(["say", "-v", "Tingting", "-o", str(src), text], check=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-ac",
            "1",
            "-ar",
            str(RATE),
            "-sample_fmt",
            "s16",
            str(wav),
        ],
        check=True,
    )
    return wav


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path)) as w:
        return w.readframes(w.getnframes())


def silence(sec: float) -> bytes:
    return b"\x00\x00" * int(sec * RATE)


def srt_ts(t: float) -> str:
    ms = round(t * 1000)
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def main() -> None:
    cfg = yaml.safe_load((ROOT / "script.yaml").read_text(encoding="utf-8"))
    CACHE.mkdir(parents=True, exist_ok=True)
    AUDIO.mkdir(parents=True, exist_ok=True)
    gap, tail = float(cfg["gap"]), float(cfg["tail"])
    timings: dict[str, dict] = {}
    srt: list[str] = []
    offset = 0.0
    idx = 1
    for scene in cfg["scenes"]:
        pcm = bytearray(silence(LEAD))
        starts, ends = [], []
        for sent in scene["sentences"]:
            clip = read_pcm(synth(spoken(sent), cfg["voice"], cfg["rate"]))
            start = len(pcm) / 2 / RATE
            pcm += clip
            end = len(pcm) / 2 / RATE
            pcm += silence(gap)
            starts.append(round(start, 3))
            ends.append(round(end, 3))
            srt.append(f"{idx}\n{srt_ts(offset + start)} --> {srt_ts(offset + end)}\n{sent}\n")
            idx += 1
        pcm += silence(tail)
        dur = len(pcm) / 2 / RATE
        with wave.open(str(AUDIO / f"{scene['id']}.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(bytes(pcm))
        timings[scene["id"]] = {"starts": starts, "ends": ends, "dur": round(dur, 3)}
        print(f"{scene['id']}: {dur:.1f}s")
        offset += dur
    (OUT / "timings.json").write_text(json.dumps(timings, ensure_ascii=False, indent=2))
    (OUT / "vibesop-intro.srt").write_text("\n".join(srt), encoding="utf-8")
    print(f"total: {offset:.1f}s")


if __name__ == "__main__":
    main()
