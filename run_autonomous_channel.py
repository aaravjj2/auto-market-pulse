#!/usr/bin/env python3
"""Master Orchestrator: Autonomous video channel pipeline with forced Dollar Devaluation content.

HYBRID STRATEGY: Supports OpenRouter API (primary) and local Ollama (fallback).
Forces specific "Dollar Devaluation" content for first run.
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


# Force this content for the first run
FORCED_METADATA = {
    "title": "Why Your Dollar Is Dying",
    "script_text": "You are working for free. You just don't know it yet. In 1970, the average American home cost twenty-three thousand dollars. Today, it is over four hundred thousand. Did houses get twenty times better? No. Your money got twenty times worse. Look at the chart behind me. This is the M2 Money Supply. See this vertical line in 2020? The government printed forty percent of all US dollars in existence in just twelve months. This isn't inflation; it is mathematical theft. When they double the supply of money, they cut the value of your labor in half. The wealthy understand this game. They don't hoard cash; they hoard assets like gold, real estate, and stocks. They borrow cheap money to buy appreciating assets, while you work harder for currency that buys less. The system is designed to punish savers and reward debtors. If you are keeping your life savings in a bank account, you are literally losing money every single second you sleep. So stop saving a dying currency. Because as long as you trade time for paper... You are working for free.",
    "visual_scenes": [
        {"start": 0, "end": 8, "filename": "vintage_1970s_home.mp4"},
        {"start": 8, "end": 25, "filename": "money_printer_brrr.mp4"},
        {"start": 25, "end": 45, "filename": "stock_market_crash_red.mp4"},
        {"start": 45, "end": 60, "filename": "gold_bars_cinematic.mp4"}
    ]
}


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
        description="Autonomous video channel pipeline orchestrator (Dollar Devaluation)"
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Output directory (default: output)"
    )
    parser.add_argument(
        "--use-forced",
        action="store_true",
        default=True,
        help="Use forced Dollar Devaluation metadata (default: True)"
    )
    parser.add_argument(
        "--skip-assets",
        action="store_true",
        help="Skip asset generation (use existing)"
    )
    args = parser.parse_args()
    
    # Create output directory structure
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(args.output_dir, f"dollar_run_{timestamp}")
    os.makedirs(run_dir, exist_ok=True)
    
    print(f"\n{'='*60}")
    print(f"Dollar Devaluation Video Pipeline")
    print(f"Run ID: {timestamp}")
    print(f"Output Directory: {run_dir}")
    print('='*60)
    
    # Phase 1: Write forced metadata
    if args.use_forced:
        print("\n[Phase 1] Writing forced metadata...")
        metadata_path = Path("data/cache/current_video_metadata.json")
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        with open(metadata_path, "w") as f:
            json.dump(FORCED_METADATA, f, indent=2)
        print(f"✓ Written metadata to {metadata_path}")
        print(f"  Title: {FORCED_METADATA['title']}")
        print(f"  Script length: {len(FORCED_METADATA['script_text'])} characters")
        print(f"  Visual scenes: {len(FORCED_METADATA['visual_scenes'])}")
        
        # Also create a story.json for compatibility
        story_json = {
            "type": "market_pulse",
            "title": FORCED_METADATA["title"],
            "bullets": [
                {"symbol": "USD", "text": FORCED_METADATA["script_text"]}
            ],
            "records": [],
            "signals": [],
            "summary_tweet": FORCED_METADATA["title"]
        }
        story_output = os.path.join(run_dir, "story.json")
        with open(story_output, "w") as f:
            json.dump(story_json, f, indent=2)
        print(f"✓ Written story.json to {story_output}")
    
    # Phase 2: Generate assets
    if not args.skip_assets:
        print("\n[Phase 2] Generating background assets...")
        run_command("python scripts/06_assets/auto_generate_media.py")
    else:
        print("\n[Phase 2] Skipping asset generation (using existing)")
    
    # Phase 3: Generate charts (using existing Manim scenes or create new)
    print("\n[Phase 3] Using existing Manim charts...")
    # For the Dollar video, we can use existing charts or create simple ones
    # For now, we'll use a placeholder chart path - user can replace this
    chart_dir = os.path.join(run_dir, "charts")
    os.makedirs(chart_dir, exist_ok=True)
    
    # Check if we have existing charts from previous runs
    existing_charts = list(Path("output/run_20260105_022120/charts").glob("*.mov")) if Path("output/run_20260105_022120/charts").exists() else []
    if existing_charts:
        # Copy first chart as placeholder
        import shutil
        chart_file = existing_charts[0]
        dest_chart = os.path.join(chart_dir, "chart_video.mov")
        shutil.copy(chart_file, dest_chart)
        print(f"✓ Using existing chart: {dest_chart}")
    else:
        # Create a simple placeholder - for now, use the first available chart file
        print("Warning: No existing charts found, chart generation skipped")
        dest_chart = None
    
    # Phase 4: Generate audio (TTS)
    print("\n[Phase 4] Generating audio with TTS...")
    audio_output = os.path.join(run_dir, "audio.wav")
    
    # Create a simple text file with the script for TTS
    script_text = FORCED_METADATA["script_text"]
    
    # Use TTS generate - we need to create a minimal story JSON for it
    timing_template = "templates/video_timing.json"
    if not os.path.exists(timing_template):
        timing_template = "templates/video_timing_short.json"
    
    run_command(
        f"python scripts/05_audio/tts_generate.py "
        f"--story {story_output} "
        f"--timing {timing_template} "
        f"--output {audio_output}"
    )
    
    # Phase 5: Generate ASS subtitles
    print("\n[Phase 5] Generating ASS subtitles...")
    subtitle_output = os.path.join(run_dir, "subtitles.ass")
    run_command(
        f"python scripts/06_assets/generate_ass.py "
        f"--story {story_output} "
        f"--timing {timing_template} "
        f"--output {subtitle_output}"
    )
    
    # Phase 6: Assemble video using FFmpeg
    print("\n[Phase 6] Assembling video with FFmpeg...")
    
    # Determine chart video - use first scene's background video if no chart
    if not dest_chart or not os.path.exists(dest_chart):
        # Use first background video as chart placeholder
        first_scene = FORCED_METADATA["visual_scenes"][0]
        bg_video = os.path.join("assets/bg", first_scene["filename"])
        if os.path.exists(bg_video):
            dest_chart = bg_video
            print(f"Using background video as chart: {dest_chart}")
        else:
            print("Error: No chart video available", file=sys.stderr)
            sys.exit(1)
    
    # For this video, we need to composite multiple background videos based on timing
    # For simplicity, use the first background video
    bg_video = os.path.join("assets/bg", FORCED_METADATA["visual_scenes"][0]["filename"])
    
    final_video_path = os.path.join(run_dir, "final_video.mp4")
    
    run_command(
        f"python scripts/04_render/assemble_ffmpeg.py "
        f"--story {story_output} "
        f"--audio {audio_output} "
        f"--chart {dest_chart} "
        f"--subtitles {subtitle_output} "
        f"--outdir {run_dir} "
        f"--background {bg_video}"
    )
    
    # Move to final location
    if os.path.exists(os.path.join(run_dir, "final_video.mp4")):
        final_output = os.path.join(run_dir, "final_video.mp4")
    else:
        final_output = None
    
    print(f"\n{'='*60}")
    if final_output and os.path.exists(final_output):
        print(f"✓ Pipeline Complete!")
        print(f"Final Video: {final_output}")
        
        # Also copy to outputs directory
        outputs_dir = Path("outputs")
        outputs_dir.mkdir(exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        final_dest = outputs_dir / f"final_video_{date_str}.mp4"
        import shutil
        shutil.copy(final_output, final_dest)
        print(f"Copied to: {final_dest}")
    else:
        print(f"⚠ Pipeline completed but final video not found")
    print(f"Run Directory: {run_dir}")
    print('='*60)
    
    return final_output


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
