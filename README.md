# The Algorithm Did This — Shorts

Rendered YouTube Shorts for [@thealgorithmdidthis](https://www.youtube.com/@thealgorithmdidthis).

- `engine/` free, offline video engine (espeak-ng + Kokoro TTS + Pillow + ffmpeg). Run `engine/setup.sh` once, then `python3 engine/render.py episodes/<file>.json videos/<file>.mp4`.
- `episodes/` beat scripts, one JSON per Short.
- `videos/` finished MP4s (public so the scheduler can fetch them).
- `episodes.json` the production log.
