#!/usr/bin/env python3
"""Safety Net: Ensures background video assets exist, generating placeholders if missing.

CRITICAL: The pipeline must never crash because of a missing file.
It must always produce something, even if it's a simple placeholder.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List

try:
    import numpy as np
    from moviepy.editor import ColorClip, VideoClip, CompositeVideoClip, concatenate_videoclips
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False
    print("Warning: MoviePy not available. Install with: pip install moviepy", file=sys.stderr)


def generate_placeholder_video(
    output_path: str,
    duration: float = 30.0,
    width: int = 1080,
    height: int = 1920,
    method: str = "noise"
) -> str:
    """Generate a placeholder background video.
    
    Args:
        output_path: Path where the video will be saved
        duration: Duration in seconds (default 30s, can be looped)
        width: Video width (default 1080)
        height: Video height (default 1920)
        method: Generation method - "noise" (animated noise) or "solid" (solid color)
        
    Returns:
        Path to generated video file
    """
    if not MOVIEPY_AVAILABLE:
        raise ImportError("MoviePy is required to generate placeholder videos")
    
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    if method == "noise":
        # Generate animated noise pattern using ColorClip segments with variation
        clips = []
        num_segments = min(int(duration * 2), 60)  # 0.5 second segments, max 60
        segment_duration = duration / num_segments if num_segments > 0 else duration
        
        base_color = (20, 20, 25)
        for i in range(num_segments):
            # Vary the color slightly between segments for animation effect
            variation = np.random.randint(-5, 5, 3)
            color = tuple(int(np.clip(base_color[j] + variation[j], 0, 255)) for j in range(3))
            segment = ColorClip(size=(width, height), color=color, duration=segment_duration)
            clips.append(segment)
        
        if len(clips) > 1:
            clip = concatenate_videoclips(clips, method="compose")
        else:
            clip = clips[0] if clips else ColorClip(size=(width, height), color=base_color, duration=duration)
    else:
        # Solid dark color (simpler fallback)
        clip = ColorClip(size=(width, height), color=(20, 20, 25), duration=duration)
    
    # Write the video
    clip.write_videofile(
        str(output_path_obj),
        codec='libx264',
        preset='ultrafast',
        fps=30,
        audio=False
    )
    clip.close()
    
    return str(output_path_obj.resolve())


def ensure_background_videos(assets_dir: str, required_files: List[str]) -> List[str]:
    """Ensure all required background video files exist, generating placeholders if missing.
    
    Args:
        assets_dir: Base assets directory (e.g., "assets")
        required_files: List of required video filenames (e.g., ["vintage_grain.mp4", "printing_press.mp4"])
        
    Returns:
        List of paths to existing or generated video files
    """
    assets_path = Path(assets_dir)
    bg_dir = assets_path / "bg"
    bg_dir.mkdir(parents=True, exist_ok=True)
    
    existing_paths = []
    
    for filename in required_files:
        file_path = bg_dir / filename
        
        if file_path.exists():
            print(f"✓ Found: {file_path}")
            existing_paths.append(str(file_path.resolve()))
        else:
            print(f"✗ Missing: {file_path} - Generating placeholder...")
            try:
                generated_path = generate_placeholder_video(
                    str(file_path),
                    duration=30.0,  # 30 second loop
                    method="noise"  # Animated noise pattern
                )
                print(f"✓ Generated placeholder: {generated_path}")
                existing_paths.append(generated_path)
            except Exception as e:
                print(f"✗ Error generating placeholder for {filename}: {e}", file=sys.stderr)
                # Even if generation fails, return the path so pipeline can try to handle it
                existing_paths.append(str(file_path))
    
    return existing_paths


def main():
    parser = argparse.ArgumentParser(
        description="Ensure background video assets exist, generating placeholders if missing"
    )
    parser.add_argument(
        "--assets-dir",
        default="assets",
        help="Base assets directory (default: assets)"
    )
    parser.add_argument(
        "--required",
        nargs="+",
        default=["vintage_grain.mp4", "printing_press.mp4", "dark_grid_loop.mp4"],
        help="List of required video files (default: vintage_grain.mp4 printing_press.mp4 dark_grid_loop.mp4)"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check if files exist, don't generate placeholders"
    )
    
    args = parser.parse_args()
    
    if args.check_only:
        # Just check and report
        assets_path = Path(args.assets_dir)
        bg_dir = assets_path / "bg"
        missing = []
        for filename in args.required:
            file_path = bg_dir / filename
            if file_path.exists():
                print(f"✓ {filename}")
            else:
                print(f"✗ {filename} (missing)")
                missing.append(filename)
        
        if missing:
            print(f"\n{len(missing)} file(s) missing. Run without --check-only to generate placeholders.")
            sys.exit(1)
        else:
            print("\nAll required files exist.")
            sys.exit(0)
    else:
        # Ensure files exist (generate if missing)
        existing_paths = ensure_background_videos(args.assets_dir, args.required)
        print(f"\nVerified {len(existing_paths)} background video file(s).")
        return existing_paths


if __name__ == "__main__":
    main()

