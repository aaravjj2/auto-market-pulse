# Auto Market Pulse

Automated short-format market-intelligence pipeline that fetches price data, generates charts and facts, ranks topic ideas, synthesizes narration (Coqui local TTS with `gTTS` fallback), and renders short social videos with styled subtitles.

## Quick start

Prerequisites:
- Python 3.11 (recommended for Coqui `TTS`) — optional if you only use `gTTS`
- `ffmpeg` installed and on PATH

Minimal example (from repository root):

```bash
# (use python3.11 if you want local Coqui TTS)
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# fetch latest prices and write cache
python scripts/01_fetch/fetch_prices.py --now

# generate story payload
python scripts/02_analyze/generate_story.py --cache data/cache/YYYYMMDD_tickers.csv --outdir output/YYYY-MM-DD

# make charts (adds PNGs and optional interactive Plotly HTML)
python scripts/03_chart/make_charts.py --cache data/cache/YYYYMMDD_tickers.csv --outdir output/YYYY-MM-DD/charts --plotly

# render short video (uses templates/video_timing_short.json)
python scripts/04_render/render_video.py \
  --story output/YYYY-MM-DD/story.json \
  --chart_meta output/YYYY-MM-DD/charts/chart_meta.json \
  --timing templates/video_timing_short.json \
  --outdir output/YYYY-MM-DD/video_short

# synthesize narration (try Coqui local backend, fallback to gTTS)
python scripts/05_audio/tts_generate.py \
  --story output/YYYY-MM-DD/story.json \
  --timing templates/video_timing_short.json \
  --output output/YYYY-MM-DD/video_short/audio.wav \
  --backend coqui

# generate ASS subtitles and (optionally) burn them in
python scripts/06_assets/generate_ass.py --story output/YYYY-MM-DD/story.json --timing templates/video_timing_short.json --output output/YYYY-MM-DD/video_short/captions.ass
ffmpeg -i short.mp4 -i audio.wav -vf ass=captions.ass -c:v copy -c:a aac output_with_audio.mp4
```

Notes
- Local Coqui `TTS` currently requires Python 3.9–3.11; the project will fall back to `gTTS` if not available.
- Output and generated media live in the `output/` directory (excluded via `.gitignore`).
- Do not commit secrets or private keys. Use environment variables or a secret manager for credentials.

Files to inspect
- `scripts/03_chart/make_charts.py` — chart creation and Plotly export
- `scripts/05_audio/tts_generate.py` — TTS backends and CLI
- `templates/video_timing_short.json` — timing for short-format videos

If you'd like, I can:
- add a short usage/demo script that runs the full pipeline on a cached dataset,
- create a GitHub release/tag, or
- add CI to run the smoke test.

License / privacy: this repository is public; ensure any sensitive files are removed before pushing.
auto-market-pulse
=================

Automated market intelligence pipeline — scaffold and starter scripts.

See `scripts/01_fetch/fetch_prices.py` for the initial fetch implementation.
