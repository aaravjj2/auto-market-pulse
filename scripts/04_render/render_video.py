#!/usr/bin/env python3
"""Assemble PNG scenes and story text into a short MP4 using moviepy.

This is a minimal renderer: it draws captions onto images then concatenates ImageClips.
"""
import argparse
import json
import os
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
import subprocess


def ensure_dir(p):
    os.makedirs(p, exist_ok=True)


def draw_caption(infile, text, outfile, fontsize=40):
    img = Image.open(infile).convert("RGBA")
    w, h = img.size
    txt_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(txt_layer)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", fontsize)
    except Exception:
        font = ImageFont.load_default()
    # wrap text if too long
    margin = 40
    x = margin
    y = h - margin - fontsize * 2
    draw.rectangle([(0, y - 10), (w, h)], fill=(0, 0, 0, 140))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))
    out = Image.alpha_composite(img, txt_layer)
    out.convert("RGB").save(outfile, quality=90)


def main(args):
    ensure_dir(args.outdir)
    with open(args.story) as f:
        story = json.load(f)
    with open(args.chart_meta) as f:
        meta = json.load(f)
    with open(args.timing) as f:
        timing = json.load(f)

    # For mapping symbol -> bullet text, use first matching bullet per symbol
    symbol_text = {}
    for b in story.get("bullets", []):
        t = b.get("text", "")
        parts = t.split()
        if parts:
            symbol_text[parts[0]] = t

    tmp_dir = os.path.join(args.outdir, "_tmp")
    ensure_dir(tmp_dir)

    scene_sec = timing.get("scene_sec", 4)

    seq_files = []

    # intro image
    intro_txt = story.get("title", "Market Pulse")
    intro_img = os.path.join(tmp_dir, "frame_0000.jpg")
    img = Image.new("RGB", (720, 1280), color=(20, 20, 20))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 64)
    except Exception:
        font = ImageFont.load_default()
    w, h = img.size
    bbox = d.textbbox((0, 0), intro_txt, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    d.text(((w - text_w) / 2, (h - text_h) / 2), intro_txt, font=font, fill=(255, 255, 255))
    img.save(intro_img)
    seq_files.append((intro_img, timing.get("intro_sec", 3)))

    idx = 1
    for s in meta.get("scenes", []):
        img_file = s.get("file")
        sym = s.get("symbol")
        caption = symbol_text.get(sym, story.get("title", ""))
        outname = os.path.join(tmp_dir, f"frame_{idx:04d}.jpg")
        draw_caption(img_file, caption, outname)
        seq_files.append((outname, scene_sec))
        idx += 1

    # outro
    outro_txt = "End — Educational content. Not financial advice."
    outro_img = os.path.join(tmp_dir, f"frame_{idx:04d}.jpg")
    img2 = Image.new("RGB", (720, 1280), color=(10, 10, 10))
    d2 = ImageDraw.Draw(img2)
    try:
        font2 = ImageFont.truetype("DejaVuSans-Bold.ttf", 32)
    except Exception:
        font2 = ImageFont.load_default()
    bbox2 = d2.textbbox((0, 0), outro_txt, font=font2)
    tw = bbox2[2] - bbox2[0]
    th = bbox2[3] - bbox2[1]
    d2.text(((w - tw) / 2, (h - th) / 2), outro_txt, font=font2, fill=(255, 255, 255))
    img2.save(outro_img)
    seq_files.append((outro_img, timing.get("outro_sec", 2)))

    # write ffmpeg concat list
    list_txt = os.path.join(tmp_dir, "list.txt")
    with open(list_txt, "w") as f:
        for fname, dur in seq_files:
            fpath = os.path.abspath(fname)
            f.write(f"file '{fpath}'\n")
            f.write(f"duration {dur}\n")
        # ffmpeg concat demuxer requires last file listed twice for correct duration
        f.write(f"file '{seq_files[-1][0]}'\n")

    outname = os.path.join(args.outdir, f"short_market_pulse_{datetime.now().strftime('%Y%m%d')}.mp4")
    # try to find a bundled ffmpeg (imageio_ffmpeg) before falling back to system ffmpeg
    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        ffmpeg_exe = get_ffmpeg_exe()
    except Exception:
        ffmpeg_exe = "ffmpeg"

    cmd = [
        ffmpeg_exe,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        list_txt,
        "-vsync",
        "vfr",
        "-pix_fmt",
        "yuv420p",
        outname,
    ]
    subprocess.run(cmd, check=True)
    print("Wrote video:", outname)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--story", required=True)
    p.add_argument("--chart_meta", required=True)
    p.add_argument("--timing", default="templates/video_timing.json")
    p.add_argument("--outdir", required=True)
    args = p.parse_args()
    main(args)
