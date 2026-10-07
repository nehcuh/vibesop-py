#!/usr/bin/env bash
# Build the VibeSOP intro video: capture → TTS → render scenes → concat.
# Output: dist/video/vibesop-intro.mp4 (+ .srt soft subtitles)
# Requires: ffmpeg, uv, Google Chrome (used by Playwright via channel="chrome").
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT=dist/video

echo "▶ capture CLI output"
.venv/bin/python scripts/video/capture.py

echo "▶ narration (edge-tts)"
uv run --no-project --quiet --with edge-tts --with pyyaml python scripts/video/tts.py

echo "▶ render scenes"
uv run --no-project --quiet --with playwright --with pyyaml --with rich \
  python scripts/video/render.py "$@"

echo "▶ concat"
: > "$OUT/concat.txt"
for f in "$OUT"/scenes/s*.mp4; do echo "file '$(basename "$f")'" >> "$OUT/concat.txt"; done
mv "$OUT/concat.txt" "$OUT/scenes/concat.txt"
ffmpeg -y -loglevel error -f concat -safe 0 -i "$OUT/scenes/concat.txt" \
  -c:v copy -af loudnorm=I=-16:TP=-1.5:LRA=11 -c:a aac -b:a 192k -ar 48000 \
  -movflags +faststart "$OUT/vibesop-intro.mp4"

ffprobe -v error -show_entries format=duration:stream=codec_name,width,height \
  -of compact "$OUT/vibesop-intro.mp4"
echo "✓ $OUT/vibesop-intro.mp4"
