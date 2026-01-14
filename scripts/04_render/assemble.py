#!/usr/bin/env python3
"""Assemble scenes into a vertical MP4 using MoviePy with Ken Burns and dynamic captions.

Features:
- Uses `h264_nvenc` when available (falls back to `libx264`).
- Applies a subtle Ken Burns zoom+pan to each static chart image.
- Creates 'Hormozi-style' dynamic subtitles: yellow text with black stroke, word-by-word timing.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import json
import math
import os
from datetime import datetime
from typing import List, Tuple

from moviepy import ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip, TextClip
import tempfile
import uuid
import numpy as np
from PIL import Image, ImageOps


def ken_burns_clip(image_path: str, duration: float, zoom=1.06, start_pos=(0.5, 0.5)):
    """Return an ImageClip with a subtle zoom-in centered on `start_pos` (fractional).

    start_pos: (x_frac, y_frac) where 0-1 indicates focal point.
    """
    # Keep this function for backward-compat, but fallback to a stable fitted ImageClip
    return make_fitted_image_clip(image_path, duration, (1080, 1920))


def make_fitted_image_clip(image_path: str, duration: float, video_size: Tuple[int, int]):
    """Load image, fit it to `video_size` using cover behavior, and return an ImageClip of given duration."""
    try:
        img = Image.open(image_path).convert('RGB')
        fitted = ImageOps.fit(img, video_size, Image.LANCZOS)
        arr = np.array(fitted)
        clip = ImageClip(arr).with_duration(duration)
        return clip
    except Exception:
        # fallback to ImageClip from path if PIL fails
        return ImageClip(image_path).with_duration(duration).resize(newsize=video_size)


def word_by_word_subtitles(text: str, start: float, duration: float, target_chunk_dur: float = 0.45) -> List[Tuple[float, float, str]]:
    """Create subtitle events by grouping words into chunks so pacing is readable.

    target_chunk_dur: desired duration per subtitle chunk in seconds (approx).
    """
    words = text.strip().split()
    if not words:
        return []
    # Determine number of chunks so each chunk is approximately target_chunk_dur
    chunks = max(1, int(max(1, round(duration / target_chunk_dur))))
    words_per_chunk = max(1, math.ceil(len(words) / chunks))
    per_chunk = duration / math.ceil(len(words) / words_per_chunk)
    items: List[Tuple[float, float, str]] = []
    t = start
    for i in range(0, len(words), words_per_chunk):
        chunk_words = words[i:i + words_per_chunk]
        chunk_text = ' '.join(chunk_words)
        items.append((t, min(t + per_chunk, start + duration), chunk_text))
        t += per_chunk
    return items


def create_subtitle_clips(sub_events: List[Tuple[float, float, str]], video_size: Tuple[int, int], font: str = "DejaVuSans-Bold.ttf"):
    clips = []
    w, h = video_size
    for (s, e, text) in sub_events:
        txt = TextClip(text=text, font=font, font_size=56, color='yellow', stroke_color='black', stroke_width=4, method='label')
        txt = txt.with_start(s).with_end(e)
        txt = txt.with_position(('center', h - 220))
        clips.append(txt)
    return clips


def choose_codec(prefer_nvenc: bool = True):
    # detect ffmpeg and whether h264_nvenc is available
    # prefer the ffmpeg used by imageio_ffmpeg (moviepy) if available
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        ffmpeg = get_ffmpeg_exe()
    except Exception:
        ffmpeg = shutil.which('ffmpeg') or 'ffmpeg'
    try:
        out = subprocess.check_output([ffmpeg, '-hide_banner', '-encoders'], stderr=subprocess.STDOUT, text=True)
        has_nvenc = 'h264_nvenc' in out
    except Exception:
        has_nvenc = False

    if prefer_nvenc and has_nvenc:
        return 'h264_nvenc'
    return 'libx264'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--chart_meta', required=True)
    p.add_argument('--story', required=True)
    p.add_argument('--audio', help='optional audio file to attach')
    p.add_argument('--out', required=True)
    p.add_argument('--codec', default=None, help='force codec (e.g., h264_nvenc or libx264)')
    args = p.parse_args()

    with open(args.chart_meta) as f:
        meta = json.load(f)
    with open(args.story) as f:
        story = json.load(f)
    timing_path = os.path.join(os.path.dirname(args.story), '..', 'templates', 'video_timing.json')
    # simple default durations
    intro_sec = 3
    scene_sec = 4
    outro_sec = 2
    try:
        import json as _j
        tfile = os.path.join(os.path.dirname(args.story), 'templates', 'video_timing.json')
        if os.path.exists(tfile):
            with open(tfile) as tf:
                t = _j.load(tf)
                intro_sec = t.get('intro_sec', intro_sec)
                scene_sec = t.get('scene_sec', scene_sec)
                outro_sec = t.get('outro_sec', outro_sec)
    except Exception:
        pass

    # Build scene clips
    clips = []
    video_size = (1080, 1920)

    # If Manim-generated clips are present in meta (list under 'manim_clips'),
    # use those mp4 files directly (do not re-render image-based clips).
    manim_clips = meta.get('manim_clips') or None
    if isinstance(manim_clips, list) and manim_clips:
        # Resolve relative paths robustly relative to the chart_meta file, cwd, and common-prefix mistakes
        meta_dir = os.path.dirname(os.path.abspath(args.chart_meta))
        resolved_parts = []
        missing = []
        for p in manim_clips:
            # absolute path
            if os.path.isabs(p) and os.path.exists(p):
                resolved_parts.append(p)
                continue

            # first try relative to chart_meta directory
            cand = os.path.join(meta_dir, p)
            if os.path.exists(cand):
                resolved_parts.append(cand)
                continue

            # then try relative to cwd
            cand2 = os.path.join(os.getcwd(), p)
            if os.path.exists(cand2):
                resolved_parts.append(cand2)
                continue

            # try stripping a leading project prefix (common incorrect path)
            if p.startswith('auto-market-pulse/'):
                stripped = p.split('auto-market-pulse/', 1)[1]
                alt = os.path.join(os.getcwd(), stripped)
                if os.path.exists(alt):
                    resolved_parts.append(alt)
                    continue

            missing.append(p)

        if resolved_parts:
            print('Assemble: using manim_clips pipeline')
            print('Resolved parts:')
            for r in resolved_parts:
                print(' -', r)
            if missing:
                print('Warning: some paths listed in chart_meta.json were missing:', missing)

            # We already have ready-to-concatenate mp4 files in `resolved_parts`.
            # No need to load VideoFileClip here (avoids requiring moviepy for concat branch).

            # If we used manim mp4s, we skip the image-based clip building below
            # and proceed to concat/attach audio.
            def render_parts_and_concat_from_files(parts, out_path, audio_path=None):
                # parts: list of absolute file paths already ready
                tmpdir = os.path.join(tempfile.gettempdir(), "amp_assemble_" + uuid.uuid4().hex)
                os.makedirs(tmpdir, exist_ok=True)
                copy_parts = []
                for i, p in enumerate(parts):
                    dest = os.path.join(tmpdir, f"part_{i:02d}.mp4")
                    # copy to tmpdir to avoid permissions/locking
                    import shutil

                    shutil.copy(p, dest)
                    copy_parts.append(dest)

                listf = os.path.join(tmpdir, 'parts.txt')
                with open(listf, 'w') as f:
                    for cp in copy_parts:
                        f.write(f"file '{os.path.abspath(cp)}'\n")

                concat_vid = os.path.join(tmpdir, 'concat.mp4')
                cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', listf, '-c', 'copy', concat_vid]
                subprocess.run(cmd, check=True)

                # Attempt to locate a word timestamps JSON to build SRT subtitles
                srt_path = None
                possible_dirs = []
                if audio_path:
                    possible_dirs.append(os.path.dirname(os.path.abspath(audio_path)))
                possible_dirs.append(meta_dir)
                possible_dirs.append(os.getcwd())

                for d in possible_dirs:
                    cand = os.path.join(d, 'audio_dollar_word_timestamps.json')
                    if os.path.exists(cand):
                        srt_path = os.path.join(tmpdir, 'captions.srt')
                        try:
                            with open(cand) as wf:
                                wj = json.load(wf)
                            words = None
                            if isinstance(wj, list):
                                words = wj
                            elif isinstance(wj, dict) and 'words' in wj:
                                words = wj['words']
                            elif isinstance(wj, dict) and 'segments' in wj:
                                words = []
                                for seg in wj['segments']:
                                    for w in seg.get('words', []):
                                        words.append(w)

                            if not words:
                                srt_path = None
                                break

                            def sec_to_srt(t):
                                h = int(t // 3600)
                                m = int((t % 3600) // 60)
                                s = int(t % 60)
                                ms = int((t - int(t)) * 1000)
                                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

                            grp = []
                            chunk_size = 3
                            for i in range(0, len(words), chunk_size):
                                slice_words = words[i:i+chunk_size]
                                start = float(slice_words[0].get('start', slice_words[0].get('t', 0)))
                                end = float(slice_words[-1].get('end', slice_words[-1].get('t', start+0.5)))
                                text = ' '.join([w.get('word', w.get('text', '')).strip() for w in slice_words])
                                grp.append((start, end, text))

                            with open(srt_path, 'w') as sf:
                                for idx, (st, en, txt) in enumerate(grp, start=1):
                                    sf.write(str(idx) + '\n')
                                    sf.write(sec_to_srt(st) + ' --> ' + sec_to_srt(en) + '\n')
                                    sf.write(txt + '\n\n')
                        except Exception:
                            srt_path = None
                        break

                processed_vid = concat_vid
                if srt_path and os.path.exists(srt_path):
                    subtitle_vid = os.path.join(tmpdir, 'concat_sub.mp4')
                    # smaller font, bottom-center alignment, and larger MarginV to place below graph
                    vf = (
                        f"subtitles={srt_path}:force_style='FontName=DejaVu Sans,Fontsize=20,PrimaryColour=&H00FFFFFF&,"
                        "Outline=1,BackColour=&H000000&,Alignment=2,MarginV=320'"
                    )
                    cmd = ['ffmpeg', '-y', '-i', concat_vid, '-vf', vf, '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-c:a', 'copy', subtitle_vid]
                    subprocess.run(cmd, check=True)
                    processed_vid = subtitle_vid

                if audio_path and os.path.exists(audio_path):
                    final_tmp = out_path + '.tmp.mp4'
                    cmd = ['ffmpeg', '-y', '-i', processed_vid, '-i', audio_path, '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k', '-shortest', final_tmp]
                    subprocess.run(cmd, check=True)
                    shutil.move(final_tmp, out_path)
                else:
                    shutil.move(processed_vid, out_path)

                try:
                    shutil.rmtree(tmpdir)
                except Exception:
                    pass

            # call the alternate pipeline
            render_parts_and_concat_from_files(resolved_parts, args.out, audio_path=args.audio)
            print('Wrote video:', args.out)
            return

    # intro
    intro_txt = story.get('title', 'Market Pulse')
    # create a simple colored intro clip
    intro_clip = TextClip(text=intro_txt, font='DejaVuSans-Bold.ttf', font_size=80, color='white', stroke_color='black', stroke_width=4, size=video_size, method='label')
    intro_clip = intro_clip.with_duration(intro_sec)
    clips.append(intro_clip)

    # Create one scene clip per bullet in the story.
    # Match each bullet's `symbol` to an entry in chart_meta; fall back to the first available image.
    meta_scenes = {s.get('symbol'): s for s in meta.get('scenes', []) if s.get('file')}
    default_img = None
    for s in meta.get('scenes', []):
        fp = s.get('file')
        if fp and os.path.exists(fp):
            default_img = fp
            break

    for b in story.get('bullets', []):
        # use per-bullet duration if present, otherwise scene_sec
        dur = b.get('dur') if isinstance(b.get('dur'), (int, float)) else scene_sec
        sym = b.get('symbol')
        img = None
        if sym and sym in meta_scenes:
            cand = meta_scenes[sym].get('file')
            if cand and os.path.exists(cand):
                img = cand
        if not img:
            img = default_img
        if not img or not os.path.exists(img):
            # skip if no image available for this bullet
            continue

        clip = ken_burns_clip(img, dur)
        bullet_text = b.get('text', '')
        if bullet_text:
            subs = word_by_word_subtitles(bullet_text, 0, dur)
            sub_clips = create_subtitle_clips(subs, video_size)
            comp = CompositeVideoClip([clip, *sub_clips], size=video_size)
        else:
            comp = clip
        clips.append(comp)

    # outro
    outro_txt = "End — Educational content. Not financial advice."
    outro_clip = TextClip(text=outro_txt, font='DejaVuSans-Bold.ttf', font_size=48, color='white', stroke_color='black', stroke_width=3, size=video_size, method='label')
    outro_clip = outro_clip.with_duration(outro_sec)
    clips.append(outro_clip)

    # By default, render each clip to a temp MP4 and use ffmpeg concat + attach audio
    def render_parts_and_concat(clips, out_path, audio_path=None):
        tmpdir = os.path.join(tempfile.gettempdir(), "amp_assemble_" + uuid.uuid4().hex)
        os.makedirs(tmpdir, exist_ok=True)
        part_files = []
        for i, c in enumerate(clips):
            part = os.path.join(tmpdir, f"part_{i:02d}.mp4")
            # render video-only part
            c.write_videofile(part, codec='libx264', fps=25, audio=False, ffmpeg_params=['-preset','fast'])
            part_files.append(part)

        listf = os.path.join(tmpdir, 'parts.txt')
        with open(listf, 'w') as f:
            for p in part_files:
                f.write(f"file '{os.path.abspath(p)}'\n")

        concat_vid = os.path.join(tmpdir, 'concat.mp4')
        cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', listf, '-c', 'copy', concat_vid]
        subprocess.run(cmd, check=True)

        if audio_path and os.path.exists(audio_path):
            final_tmp = out_path + '.tmp.mp4'
            cmd = ['ffmpeg', '-y', '-i', concat_vid, '-i', audio_path, '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k', '-shortest', final_tmp]
            subprocess.run(cmd, check=True)
            shutil.move(final_tmp, out_path)
        else:
            shutil.move(concat_vid, out_path)

        # cleanup
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass

    # ensure output dir exists
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)

    # call the robust render+concat pipeline
    render_parts_and_concat(clips, args.out, audio_path=args.audio)
    print('Wrote video:', args.out)


if __name__ == '__main__':
    main()
