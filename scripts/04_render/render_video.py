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
    # leave space for optional badge drawn by caller: if outfile filename contains '__badge__', draw it
    if "__badge__" in outfile:
        try:
            badge = outfile.split("__badge__", 1)[1]
            # truncate
            badge = badge.replace('.jpg', '')[:40]
            bx = w - 20
            by = 40
            bw = 420
            bh = 80
            # badge background
            draw.rounded_rectangle([(bx - bw, by - 10), (bx, by + bh)], radius=12, fill=(220, 50, 50, 220))
            try:
                bf = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
            except Exception:
                bf = ImageFont.load_default()
            draw.text((bx - bw + 18, by + 10), badge, font=bf, fill=(255, 255, 255, 255))
        except Exception:
            pass
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

    # For mapping symbol -> bullet dict (text + signals)
    symbol_map = {}
    for b in story.get("bullets", []):
        sym = b.get("symbol") or (b.get("text", "").split()[0] if b.get("text") else None)
        if sym:
            symbol_map[sym] = b

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
        bullet = symbol_map.get(sym, {})
        caption = bullet.get("text") or story.get("title", "")
        # badge text if signals exist
        badge = None
        if bullet.get("signals"):
            badge = bullet["signals"][0].get("narrative")
        outname = os.path.join(tmp_dir, f"frame_{idx:04d}.jpg")
        # if badge, encode into filename so draw_caption can optionally render it
        if badge:
            safe = badge.replace(' ', '_').replace('/', '_')
            outname = outname.replace('.jpg', f"__badge__{safe}.jpg")
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

    # try to use generated title if available (signals/title.json near story)
    outname_title = None
    try:
        story_dir = os.path.dirname(os.path.abspath(args.story))
        title_path = os.path.join(story_dir, "signals", "title.json")
        if os.path.exists(title_path):
            with open(title_path) as tf:
                tj = json.load(tf)
                cand = tj.get("candidates", [])
                if cand:
                    outname_title = cand[0].get("title")
    except Exception:
        outname_title = None

    if outname_title:
        # sanitize for filename
        slug = ''.join([c for c in outname_title if c.isalnum() or c in (' ', '-', '_')]).rstrip()
        slug = slug.replace(' ', '_')[:80]
        outname = os.path.join(args.outdir, f"short_market_pulse_{datetime.now().strftime('%Y%m%d')}_{slug}.mp4")
        intro_txt = outname_title
    else:
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
