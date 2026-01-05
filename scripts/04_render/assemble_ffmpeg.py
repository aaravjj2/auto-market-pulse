#!/usr/bin/env python3
"""FFmpeg-based video assembly: Background + Manim Chart + Audio + ASS Subtitles.

Replaces MoviePy-based rendering with direct FFmpeg subprocess calls for better
Windows compatibility and performance. Uses NVIDIA hardware encoding (h264_nvenc).
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

# Import asset manager for background selection
sys.path.insert(0, str(Path(__file__).parent.parent / "06_assets"))
try:
    from asset_manager import AssetManager
    ASSET_MANAGER_AVAILABLE = True
except ImportError:
    ASSET_MANAGER_AVAILABLE = False


def get_ffmpeg():
    """Get FFmpeg executable path."""
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def detect_codec(ffmpeg_exe: str) -> str:
    """Detect available codec, prefer h264_nvenc."""
    try:
        result = subprocess.run(
            [ffmpeg_exe, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if "h264_nvenc" in result.stdout:
            return "h264_nvenc"
    except Exception:
        pass
    return "libx264"


def assemble_ffmpeg(
    background_video: str,
    chart_video: str,
    audio_file: str,
    subtitle_ass: str,
    output_path: str,
    codec: str = "h264_nvenc",
    overlay_opacity: float = 0.6,
    bg_loop: bool = True
) -> str:
    """Assemble video using FFmpeg filter_complex.
    
    Args:
        background_video: Path to background video file
        chart_video: Path to Manim chart video (.mov with transparency) or image sequence
        audio_file: Path to audio file
        subtitle_ass: Path to ASS subtitle file
        output_path: Output video path
        codec: Video codec (h264_nvenc or libx264)
        overlay_opacity: Opacity for dark overlay (0.0-1.0)
        bg_loop: Whether to loop background video
        
    Returns:
        Path to output video file
    """
    ffmpeg = get_ffmpeg()
    
    # Get audio duration to determine video length
    try:
        probe_cmd = [
            ffmpeg, "-i", audio_file,
            "-hide_banner", "-show_entries", "format=duration",
            "-v", "quiet", "-of", "csv=p=0"
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
        audio_duration = float(result.stdout.strip())
    except Exception:
        audio_duration = 30.0  # Default fallback
    
    # Ensure output directory exists
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    # Build filter_complex string
    filters = []
    
    # Input 0: Background video
    # Scale and loop if needed
    if bg_loop:
        filters.append(f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,loop=loop=-1:size=1:start=0,setpts=PTS-STARTPTS[bg]")
    else:
        filters.append(f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setpts=PTS-STARTPTS[bg]")
    
    # Dark overlay for text readability
    overlay_r = int((1.0 - overlay_opacity) * 255)
    filters.append(f"color=c=black:s=1080x1920:d={audio_duration}[overlay]")
    filters.append(f"[bg][overlay]blend=all_mode=multiply:all_opacity={overlay_opacity}[bg_dark]")
    
    # Input 1: Chart video (transparent)
    # Scale to match, preserve aspect ratio
    filters.append(f"[1:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setpts=PTS-STARTPTS[chart]")
    
    # Overlay chart on background
    filters.append(f"[bg_dark][chart]overlay=0:0:shortest=1[composite]")
    
    # Burn in ASS subtitles
    subtitle_path_escaped = subtitle_ass.replace("\\", "\\\\").replace(":", "\\:")
    filters.append(f"[composite]subtitles={subtitle_path_escaped}[final]")
    
    filter_complex = ";".join(filters)
    
    # Build FFmpeg command
    cmd = [
        ffmpeg,
        "-y",  # Overwrite output
        "-i", background_video,  # Input 0: Background
        "-i", chart_video,  # Input 1: Chart video
        "-i", audio_file,  # Input 2: Audio
        "-filter_complex", filter_complex,
        "-map", "[final]",  # Map the final video stream
        "-map", "2:a",  # Map audio from input 2
        "-c:v", codec,
    ]
    
    # Codec-specific options
    if codec == "h264_nvenc":
        cmd.extend([
            "-preset", "fast",
            "-rc", "vbr",
            "-cq", "23",
            "-b:v", "5M",
            "-maxrate", "10M",
            "-bufsize", "10M",
        ])
    else:
        cmd.extend([
            "-preset", "ultrafast",
            "-crf", "23",
        ])
    
    cmd.extend([
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",  # End when shortest input ends
        "-r", "30",  # Frame rate
        str(output_path_obj)
    ])
    
    # Execute FFmpeg
    print(f"Running FFmpeg command:")
    print(" ".join([shlex.quote(arg) for arg in cmd]))
    print()
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        print(f"\n✓ Successfully created video: {output_path}")
        return str(output_path_obj.resolve())
    except subprocess.CalledProcessError as e:
        print(f"\n✗ FFmpeg failed with exit code {e.returncode}", file=sys.stderr)
        raise
    except Exception as e:
        print(f"\n✗ Error running FFmpeg: {e}", file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Assemble video using FFmpeg: Background + Chart + Audio + Subtitles"
    )
    parser.add_argument("--story", required=True, help="Story JSON file")
    parser.add_argument("--audio", required=True, help="Audio WAV file")
    parser.add_argument("--chart", required=True, help="Chart video (.mov/.mp4) or image sequence directory")
    parser.add_argument("--subtitles", required=True, help="ASS subtitle file")
    parser.add_argument("--outdir", required=True, help="Output directory")
    parser.add_argument("--background", help="Background video file (overrides asset manager)")
    parser.add_argument("--keywords", nargs="+", help="Keywords for asset manager background selection")
    parser.add_argument("--codec", choices=["h264_nvenc", "libx264"], help="Video codec (default: auto-detect)")
    parser.add_argument("--overlay-opacity", type=float, default=0.6, help="Dark overlay opacity (0.0-1.0)")
    parser.add_argument("--no-bg-loop", action="store_true", help="Don't loop background video")
    
    args = parser.parse_args()
    
    # Determine background video
    if args.background:
        bg_video = args.background
    elif ASSET_MANAGER_AVAILABLE and args.keywords:
        asset_manager = AssetManager()
        bg_video = asset_manager.get_background(args.keywords)
    else:
        # Fallback to default
        script_dir = Path(__file__).parent.parent.parent
        bg_video = str(script_dir / "assets" / "bg" / "dark_grid_loop.mp4")
    
    if not os.path.exists(bg_video):
        print(f"Error: Background video not found: {bg_video}", file=sys.stderr)
        sys.exit(1)
    
    # Check other inputs
    if not os.path.exists(args.audio):
        print(f"Error: Audio file not found: {args.audio}", file=sys.stderr)
        sys.exit(1)
    
    if not os.path.exists(args.chart):
        print(f"Error: Chart video not found: {args.chart}", file=sys.stderr)
        sys.exit(1)
    
    if not os.path.exists(args.subtitles):
        print(f"Error: Subtitle file not found: {args.subtitles}", file=sys.stderr)
        sys.exit(1)
    
    # Determine codec
    ffmpeg_exe = get_ffmpeg()
    if args.codec:
        codec = args.codec
    else:
        codec = detect_codec(ffmpeg_exe)
        print(f"Auto-detected codec: {codec}")
    
    # Generate output filename
    output_dir = Path(args.outdir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "final_video.mp4"
    
    # Assemble video
    try:
        result_path = assemble_ffmpeg(
            background_video=bg_video,
            chart_video=args.chart,
            audio_file=args.audio,
            subtitle_ass=args.subtitles,
            output_path=str(output_path),
            codec=codec,
            overlay_opacity=args.overlay_opacity,
            bg_loop=not args.no_bg_loop
        )
        print(f"\n✓ Video assembly complete: {result_path}")
    except Exception as e:
        print(f"\n✗ Video assembly failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

