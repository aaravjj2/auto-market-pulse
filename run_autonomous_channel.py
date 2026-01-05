#!/usr/bin/env python3
"""Master Orchestrator: Autonomous video channel pipeline.

Orchestrates the full pipeline:
1. Fetch -> Write (with visual keywords) -> Ensure Assets -> Chart -> TTS -> Assemble

Connects visual_keywords from Phase 1 into AssetManager for background selection.
Final output: outputs/final_video_[date].mp4
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Ensure we're in the project root
ROOT = Path(__file__).parent.resolve()
os.chdir(ROOT)


def run_command(cmd: str, check: bool = True) -> int:
    """Run a shell command and return exit code."""
    print(f"\n{'='*60}")
    print(f"RUN: {cmd}")
    print('='*60)
    result = subprocess.run(cmd, shell=True)
    if check and result.returncode != 0:
        print(f"\n✗ Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Autonomous video channel pipeline orchestrator"
    )
    parser.add_argument(
        "--symbols",
        help="Comma-separated list of symbols (e.g., SPY,GLD,SLV)"
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Output directory (default: output)"
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Skip data fetching (use existing cache)"
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OLLAMA_MODEL", "llama3"),
        help="Ollama model name (default: llama3)"
    )
    args = parser.parse_args()
    
    # Create output directory structure
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(args.output_dir, f"run_{timestamp}")
    os.makedirs(run_dir, exist_ok=True)
    
    print(f"\n{'='*60}")
    print(f"Autonomous Video Channel Pipeline")
    print(f"Run ID: {timestamp}")
    print(f"Output Directory: {run_dir}")
    print('='*60)
    
    # Phase 0: Fetch data (if not skipped)
    if not args.skip_fetch:
        print("\n[Phase 0] Fetching market data...")
        run_command("python scripts/01_fetch/fetch_prices.py --now")
    
    # Get the latest cache file
    cache_dir = Path("data/cache")
    cache_files = sorted(cache_dir.glob("*.csv"))
    if not cache_files:
        print("✗ Error: No cache files found. Run fetch first or remove --skip-fetch")
        sys.exit(1)
    cache_path = cache_files[-1]
    print(f"Using cache: {cache_path}")
    
    # Phase 1: Write script with visual keywords
    print("\n[Phase 1] Generating script with visual keywords...")
    story_output = os.path.join(run_dir, "story.json")
    symbols_arg = f"--symbols {args.symbols}" if args.symbols else ""
    run_command(
        f"python scripts/02_analyze/ai_writer.py "
        f"--cache {cache_path} "
        f"--output {story_output} "
        f"{symbols_arg} "
        f"--model {args.model}"
    )
    
    # Load metadata to get visual keywords
    metadata_path = Path("data/cache/current_video_metadata.json")
    if metadata_path.exists():
        with open(metadata_path) as f:
            metadata = json.load(f)
        visual_keywords = metadata.get("visual_keywords", [])
        print(f"Visual keywords: {visual_keywords}")
    else:
        print("Warning: Metadata file not found, using default keywords")
        visual_keywords = ["market", "finance", "chart"]
    
    # Phase 2: Ensure assets exist
    print("\n[Phase 2] Ensuring background assets exist...")
    run_command(
        "python scripts/06_assets/ensure_assets.py "
        "--required vintage_grain.mp4 printing_press.mp4 dark_grid_loop.mp4"
    )
    
    # Phase 3: Generate charts (Manim with transparency)
    print("\n[Phase 3] Generating Manim charts with transparency...")
    charts_dir = os.path.join(run_dir, "charts")
    os.makedirs(charts_dir, exist_ok=True)
    
    # Check if Manim is available, otherwise fallback to old method
    try:
        run_command(
            f"python scripts/03_chart/make_charts.py "
            f"--story {story_output} "
            f"--cache {cache_path} "
            f"--outdir {charts_dir} "
            f"--format mov"
        )
        chart_meta_path = os.path.join(charts_dir, "chart_meta.json")
        # Check if manim_clips exist in metadata
        with open(chart_meta_path) as f:
            chart_meta = json.load(f)
        manim_clips = chart_meta.get("manim_clips", [])
        if not manim_clips:
            print("Warning: No Manim clips found, may need to use fallback")
    except Exception as e:
        print(f"Warning: Chart generation had issues: {e}")
        # Continue with pipeline - assemble_layers can handle missing files
    
    # Phase 4: Generate audio (TTS)
    print("\n[Phase 4] Generating audio with TTS...")
    audio_output = os.path.join(run_dir, "audio.wav")
    timing_template = "templates/video_timing.json"
    if not os.path.exists(timing_template):
        timing_template = "templates/video_timing_short.json"
    run_command(
        f"python scripts/05_audio/tts_generate.py "
        f"--story {story_output} "
        f"--timing {timing_template} "
        f"--output {audio_output}"
    )
    
    # Phase 5: Assemble layers (Background + Manim + Subtitles)
    print("\n[Phase 5] Assembling video layers...")
    final_video_path = os.path.join(run_dir, f"final_video_{timestamp}.mp4")
    
    # Determine Manim input (use first clip if available, or fallback)
    if manim_clips and os.path.exists(manim_clips[0]):
        manim_input = manim_clips[0]
    else:
        # Fallback: try to find any chart file
        chart_files = list(Path(charts_dir).glob("*.mov")) + list(Path(charts_dir).glob("*.png"))
        if chart_files:
            manim_input = str(chart_files[0])
            if manim_input.endswith('.png'):
                # If it's a PNG, use the directory
                manim_input = charts_dir
        else:
            print("Warning: No Manim output found, using placeholder")
            manim_input = charts_dir  # Will generate error but continue
    
    # Look for subtitle JSON (word timestamps from TTS)
    subtitle_json = None
    subtitle_candidates = [
        os.path.join(run_dir, "audio_word_timestamps.json"),
        os.path.join(os.path.dirname(audio_output), "audio_dollar_word_timestamps.json"),
        "data/cache/audio_word_timestamps.json",
    ]
    for cand in subtitle_candidates:
        if os.path.exists(cand):
            subtitle_json = cand
            break
    
    keywords_arg = " ".join(visual_keywords) if visual_keywords else ""
    run_command(
        f"python scripts/04_render/assemble_layers.py "
        f"--manim {manim_input} "
        f"--audio {audio_output} "
        f"--output {final_video_path} "
        f"--keywords {keywords_arg} "
        + (f"--subtitle-json {subtitle_json} " if subtitle_json else "")
    )
    
    print(f"\n{'='*60}")
    print(f"✓ Pipeline Complete!")
    print(f"Final Video: {final_video_path}")
    print(f"Run Directory: {run_dir}")
    print('='*60)
    
    # Also save to outputs/final_video_[date].mp4 as requested
    outputs_dir = Path("outputs")
    outputs_dir.mkdir(exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    final_output_path = outputs_dir / f"final_video_{date_str}.mp4"
    
    if os.path.exists(final_video_path):
        import shutil
        shutil.copy(final_video_path, final_output_path)
        print(f"Copied to: {final_output_path}")
    
    return final_video_path


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nPipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Pipeline failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

