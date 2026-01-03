#!/usr/bin/env python3
"""Run a smoke test: fetch -> analyze -> charts -> render -> assets.
Exits non-zero on failure.
"""
import subprocess
import sys
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
os.chdir(ROOT)

def run(cmd):
    print('RUN:', cmd)
    r = subprocess.run(cmd, shell=True)
    if r.returncode != 0:
        print('FAILED:', cmd)
        sys.exit(r.returncode)

def main():
    # use existing cache if present
    run('python scripts/01_fetch/fetch_prices.py --now')
    cache = sorted(os.listdir('data/cache'))[-1]
    cache_path = os.path.join('data/cache', cache)
    outdir = os.path.join('output', 'smoke_test')
    run(f'python scripts/02_analyze/generate_story.py --cache {cache_path} --output {outdir}/story.json')
    run(f'python scripts/03_chart/make_charts.py --story {outdir}/story.json --cache {cache_path} --outdir {outdir}/charts')
    # detect signals and generate titles
    run(f'python scripts/08_signals/detect_signals.py --cache {cache_path} --outdir {outdir}/signals')
    run(f'python scripts/08_signals/generate_title.py --signals {outdir}/signals/signals.json --out {outdir}/signals/title.json')
    run(f'python scripts/04_render/render_video.py --story {outdir}/story.json --chart_meta {outdir}/charts/chart_meta.json --outdir {outdir}/video')
    run(f'python scripts/06_assets/make_thumbnail.py --chart {outdir}/charts/scene_01_SPY_price.png --headline "Smoke Test" --output {outdir}/thumbnail.png')
    run(f'python scripts/06_assets/generate_ass.py --story {outdir}/story.json --timing templates/video_timing_short.json --output {outdir}/captions.ass')
    print('SMOKE TEST COMPLETE')

if __name__ == '__main__':
    main()
