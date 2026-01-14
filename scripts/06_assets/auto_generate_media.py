#!/usr/bin/env python3
"""Auto-generate placeholder background videos using MoviePy.

Creates 4 specific background videos for the "Dollar Devaluation" video:
- vintage_1970s_home.mp4 (Sepia-tone)
- money_printer_brrr.mp4 (Green)
- stock_market_crash_red.mp4 (Red pulsing)
- gold_bars_cinematic.mp4 (Gold/Yellow)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from moviepy.editor import ColorClip, concatenate_videoclips
    import numpy as np
    MOVIEPY_AVAILABLE = True
    HAS_TEXTCLIP = False  # TextClip requires ImageMagick, skip for now
    try:
        from moviepy.editor import TextClip, CompositeVideoClip
        HAS_TEXTCLIP = True
    except Exception:
        pass
except ImportError:
    MOVIEPY_AVAILABLE = False
    print("Error: MoviePy is required. Install with: pip install moviepy", file=sys.stderr)
    sys.exit(1)


def generate_vintage_home(output_path: str, duration: float = 30.0) -> str:
    """Generate sepia-tone vintage 1970s home background."""
    width, height = 1080, 1920
    
    # Sepia-tone background (warm brown/orange)
    bg_color = (139, 90, 43)  # Sepia brown
    final = ColorClip(size=(width, height), color=bg_color, duration=duration)
    
    final.write_videofile(
        str(output_path),
        codec='libx264',
        preset='ultrafast',
        fps=30,
        audio=False
    )
    final.close()
    return str(output_path)


def generate_money_printer(output_path: str, duration: float = 30.0) -> str:
    """Generate green money printer background."""
    width, height = 1080, 1920
    
    # Bright green background
    bg_color = (0, 150, 0)  # Green
    final = ColorClip(size=(width, height), color=bg_color, duration=duration)
    
    final.write_videofile(
        str(output_path),
        codec='libx264',
        preset='ultrafast',
        fps=30,
        audio=False
    )
    final.close()
    return str(output_path)


def generate_market_crash(output_path: str, duration: float = 30.0) -> str:
    """Generate red pulsing market crash background."""
    width, height = 1080, 1920
    
    # Create pulsing red effect using multiple clips
    segments = []
    num_segments = 30  # 1 second segments
    segment_duration = duration / num_segments
    
    for i in range(num_segments):
        # Vary intensity for pulsing effect
        intensity = 0.7 + 0.3 * np.sin(i * np.pi / 5)  # Pulse every 5 segments
        r = int(200 * intensity)
        g = int(50 * intensity)
        b = int(50 * intensity)
        segment = ColorClip(size=(width, height), color=(r, g, b), duration=segment_duration)
        segments.append(segment)
    
    final = concatenate_videoclips(segments, method="compose")
    
    final.write_videofile(
        str(output_path),
        codec='libx264',
        preset='ultrafast',
        fps=30,
        audio=False
    )
    final.close()
    return str(output_path)


def generate_gold_bars(output_path: str, duration: float = 30.0) -> str:
    """Generate gold/yellow cinematic background."""
    width, height = 1080, 1920
    
    # Gold/yellow background
    bg_color = (212, 175, 55)  # Gold
    final = ColorClip(size=(width, height), color=bg_color, duration=duration)
    
    final.write_videofile(
        str(output_path),
        codec='libx264',
        preset='ultrafast',
        fps=30,
        audio=False
    )
    final.close()
    return str(output_path)


def generate_all_assets(assets_dir: str = "assets/bg") -> dict:
    """Generate all 4 required background videos.
    
    Returns:
        Dict mapping filenames to generated paths
    """
    assets_path = Path(assets_dir)
    assets_path.mkdir(parents=True, exist_ok=True)
    
    generated = {}
    
    # Generate each video
    videos = [
        ("vintage_1970s_home.mp4", generate_vintage_home),
        ("money_printer_brrr.mp4", generate_money_printer),
        ("stock_market_crash_red.mp4", generate_market_crash),
        ("gold_bars_cinematic.mp4", generate_gold_bars),
    ]
    
    for filename, generator_func in videos:
        output_path = assets_path / filename
        if output_path.exists():
            print(f"✓ {filename} already exists, skipping...")
            generated[filename] = str(output_path.resolve())
        else:
            print(f"Generating {filename}...")
            try:
                result_path = generator_func(str(output_path), duration=30.0)
                generated[filename] = result_path
                print(f"✓ Generated {filename}")
            except Exception as e:
                print(f"✗ Error generating {filename}: {e}", file=sys.stderr)
                generated[filename] = str(output_path)  # Return path even if generation failed
    
    return generated


def main():
    parser = argparse.ArgumentParser(
        description="Auto-generate placeholder background videos for Dollar Devaluation video"
    )
    parser.add_argument(
        "--assets-dir",
        default="assets/bg",
        help="Assets directory (default: assets/bg)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate videos even if they exist"
    )
    
    args = parser.parse_args()
    
    if not MOVIEPY_AVAILABLE:
        print("Error: MoviePy is required", file=sys.stderr)
        sys.exit(1)
    
    if args.force:
        # Remove existing files
        assets_path = Path(args.assets_dir)
        for filename in ["vintage_1970s_home.mp4", "money_printer_brrr.mp4", 
                        "stock_market_crash_red.mp4", "gold_bars_cinematic.mp4"]:
            filepath = assets_path / filename
            if filepath.exists():
                filepath.unlink()
    
    generated = generate_all_assets(args.assets_dir)
    
    print(f"\n✓ Generated {len(generated)} background video(s)")
    for filename, path in generated.items():
        print(f"  - {filename}: {path}")


if __name__ == "__main__":
    main()

