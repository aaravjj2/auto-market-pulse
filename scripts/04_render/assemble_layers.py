#!/usr/bin/env python3
"""Broadcast Quality "Sandwich" Compositor: Assembles three-layer video composition.

Layer 0 (Background): Background video with dark overlay for text readability
Layer 1 (Data): Transparent Manim video/animation overlay
Layer 2 (Subtitles): Hormozi-style captions (Yellow text, black stroke)

Optimized for Windows/NVIDIA RTX with hardware decoding when available.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

try:
    from moviepy.editor import (
        VideoFileClip,
        ImageSequenceClip,
        CompositeVideoClip,
        ColorClip,
        AudioFileClip,
        TextClip,
    )
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False
    print("Warning: MoviePy not available. Install with: pip install moviepy", file=sys.stderr)

# Import asset manager
sys.path.insert(0, str(Path(__file__).parent.parent / "06_assets"))
try:
    from asset_manager import AssetManager
    ASSET_MANAGER_AVAILABLE = True
except ImportError:
    ASSET_MANAGER_AVAILABLE = False
    print("Warning: asset_manager not available", file=sys.stderr)


def choose_codec(prefer_nvenc: bool = True) -> str:
    """Detect available codec, preferring NVIDIA hardware acceleration.
    
    Args:
        prefer_nvenc: If True, prefer h264_nvenc when available
        
    Returns:
        Codec name string (h264_nvenc or libx264)
    """
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        ffmpeg = get_ffmpeg_exe()
    except Exception:
        ffmpeg = shutil.which('ffmpeg') or 'ffmpeg'
    
    try:
        out = subprocess.check_output(
            [ffmpeg, '-hide_banner', '-encoders'],
            stderr=subprocess.STDOUT,
            text=True
        )
        has_nvenc = 'h264_nvenc' in out
    except Exception:
        has_nvenc = False
    
    if prefer_nvenc and has_nvenc:
        return 'h264_nvenc'
    return 'libx264'


def load_manim_clip(manim_path: str, duration: Optional[float] = None) -> VideoFileClip:
    """Load Manim output (mov with alpha or PNG sequence) as VideoFileClip.
    
    Args:
        manim_path: Path to .mov file or directory containing PNG sequence
        duration: Optional duration to set (for looping if needed)
        
    Returns:
        VideoFileClip with alpha channel preserved
    """
    manim_path_obj = Path(manim_path)
    
    if manim_path_obj.is_file() and manim_path_obj.suffix.lower() == '.mov':
        # Load .mov file (ProRes 4444 with alpha)
        clip = VideoFileClip(str(manim_path_obj), has_mask=True)
        if duration:
            # Loop if needed to match duration
            if clip.duration < duration:
                clip = clip.loop(duration=duration)
            else:
                clip = clip.subclip(0, duration)
        return clip
    
    elif manim_path_obj.is_dir():
        # Load PNG sequence
        png_files = sorted([f for f in manim_path_obj.iterdir() if f.suffix.lower() == '.png'])
        if not png_files:
            raise ValueError(f"No PNG files found in {manim_path}")
        
        # Assume 30 fps for PNG sequences (match Manim config)
        clip = ImageSequenceClip([str(f) for f in png_files], fps=30)
        if duration:
            if clip.duration < duration:
                clip = clip.loop(duration=duration)
            else:
                clip = clip.subclip(0, duration)
        return clip
    
    else:
        raise ValueError(f"Invalid Manim path: {manim_path} (must be .mov file or directory)")


def create_subtitle_clips(
    subtitle_events: List[Tuple[float, float, str]],
    video_size: Tuple[int, int],
    font: str = "DejaVuSans-Bold"
) -> List[TextClip]:
    """Create Hormozi-style subtitle clips (Yellow text, black stroke).
    
    Args:
        subtitle_events: List of (start_time, end_time, text) tuples
        video_size: (width, height) tuple for video dimensions
        font: Font name for subtitles
        
    Returns:
        List of TextClip instances
    """
    clips = []
    w, h = video_size
    
    for start, end, text in subtitle_events:
        txt_clip = TextClip(
            text=text,
            font=font,
            font_size=56,
            color='yellow',
            stroke_color='black',
            stroke_width=4,
            method='label'
        )
        txt_clip = txt_clip.with_start(start).with_end(end)
        txt_clip = txt_clip.with_position(('center', h - 220))
        clips.append(txt_clip)
    
    return clips


def load_subtitles_from_json(json_path: str, chunk_size: int = 3) -> List[Tuple[float, float, str]]:
    """Load subtitle events from word timestamps JSON file.
    
    Args:
        json_path: Path to JSON file with word timestamps
        chunk_size: Number of words per subtitle chunk
        
    Returns:
        List of (start, end, text) tuples
    """
    with open(json_path) as f:
        data = json.load(f)
    
    words = []
    if isinstance(data, list):
        words = data
    elif isinstance(data, dict):
        if 'words' in data:
            words = data['words']
        elif 'segments' in data:
            for seg in data['segments']:
                words.extend(seg.get('words', []))
    
    if not words:
        return []
    
    events = []
    for i in range(0, len(words), chunk_size):
        chunk_words = words[i:i + chunk_size]
        start = float(chunk_words[0].get('start', chunk_words[0].get('t', 0)))
        end = float(chunk_words[-1].get('end', chunk_words[-1].get('t', start + 0.5)))
        text = ' '.join([w.get('word', w.get('text', '')).strip() for w in chunk_words])
        events.append((start, end, text))
    
    return events


def assemble_layers(
    manim_path: str,
    audio_path: str,
    output_path: str,
    keywords: Optional[List[str]] = None,
    subtitle_json: Optional[str] = None,
    subtitle_events: Optional[List[Tuple[float, float, str]]] = None,
    overlay_opacity: float = 0.6,
    codec: Optional[str] = None,
    preset: str = 'ultrafast'
) -> str:
    """Assemble three-layer video composition.
    
    Args:
        manim_path: Path to Manim output (.mov or PNG sequence directory)
        audio_path: Path to audio file
        output_path: Output video file path
        keywords: Keywords for asset manager background selection
        subtitle_json: Path to JSON file with word timestamps (optional)
        subtitle_events: List of (start, end, text) tuples (optional, overrides subtitle_json)
        overlay_opacity: Opacity of dark overlay (0.0-1.0, default 0.6)
        codec: Video codec (auto-detect if None)
        preset: Encoding preset (default 'ultrafast' for speed)
        
    Returns:
        Path to output video file
    """
    if not MOVIEPY_AVAILABLE:
        raise ImportError("MoviePy is required. Install with: pip install moviepy")
    
    # Load audio to determine duration
    audio_clip = AudioFileClip(audio_path)
    target_duration = audio_clip.duration
    
    # Layer 0: Background video with dark overlay
    if ASSET_MANAGER_AVAILABLE:
        asset_manager = AssetManager()
        bg_path = asset_manager.get_background(keywords or [])
    else:
        # Fallback to default
        script_dir = Path(__file__).parent.parent.parent
        bg_path = str(script_dir / "assets" / "bg" / "dark_grid_loop.mp4")
    
    if not os.path.exists(bg_path):
        raise FileNotFoundError(f"Background video not found: {bg_path}")
    
    bg_clip = VideoFileClip(bg_path)
    
    # Loop background to match audio duration
    if bg_clip.duration < target_duration:
        bg_clip = bg_clip.loop(duration=target_duration)
    else:
        bg_clip = bg_clip.subclip(0, target_duration)
    
    # Apply dark overlay for text readability
    overlay = ColorClip(
        size=bg_clip.size,
        color=(0, 0, 0),
        duration=target_duration
    ).set_opacity(overlay_opacity)
    
    bg_composite = CompositeVideoClip([bg_clip, overlay])
    
    # Layer 1: Manim data overlay (transparent)
    manim_clip = load_manim_clip(manim_path, duration=target_duration)
    
    # Layer 2: Subtitles
    subtitle_clips = []
    if subtitle_events:
        subtitle_clips = create_subtitle_clips(subtitle_events, bg_clip.size)
    elif subtitle_json and os.path.exists(subtitle_json):
        events = load_subtitles_from_json(subtitle_json)
        subtitle_clips = create_subtitle_clips(events, bg_clip.size)
    
    # Composite all layers: Background + Overlay, then Manim, then Subtitles
    final_clip = CompositeVideoClip([bg_composite, manim_clip] + subtitle_clips)
    final_clip = final_clip.set_duration(target_duration)
    final_clip = final_clip.set_audio(audio_clip)
    
    # Choose codec
    if codec is None:
        codec = choose_codec(prefer_nvenc=True)
    
    # Ensure output directory exists
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    # Export final video
    final_clip.write_videofile(
        str(output_path_obj),
        codec=codec,
        preset=preset,
        fps=30,
        audio_codec='aac',
        audio_bitrate='128k'
    )
    
    # Cleanup
    bg_clip.close()
    manim_clip.close()
    audio_clip.close()
    final_clip.close()
    
    return str(output_path_obj.resolve())


def main():
    parser = argparse.ArgumentParser(
        description="Assemble three-layer video composition with background, Manim data, and subtitles"
    )
    parser.add_argument('--manim', required=True, help='Path to Manim output (.mov or PNG directory)')
    parser.add_argument('--audio', required=True, help='Path to audio file')
    parser.add_argument('--output', required=True, help='Output video file path')
    parser.add_argument('--keywords', nargs='+', help='Keywords for background selection (e.g., money housing)')
    parser.add_argument('--subtitle-json', help='Path to JSON file with word timestamps')
    parser.add_argument('--overlay-opacity', type=float, default=0.6, help='Dark overlay opacity (0.0-1.0)')
    parser.add_argument('--codec', choices=['h264_nvenc', 'libx264'], help='Force video codec')
    parser.add_argument('--preset', default='ultrafast', help='Encoding preset (default: ultrafast)')
    
    args = parser.parse_args()
    
    try:
        output_file = assemble_layers(
            manim_path=args.manim,
            audio_path=args.audio,
            output_path=args.output,
            keywords=args.keywords,
            subtitle_json=args.subtitle_json,
            overlay_opacity=args.overlay_opacity,
            codec=args.codec,
            preset=args.preset
        )
        print(f"Successfully created video: {output_file}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

