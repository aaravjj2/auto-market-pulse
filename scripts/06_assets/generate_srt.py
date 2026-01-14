#!/usr/bin/env python3
"""Generate an SRT file from story JSON and video timing template."""
import argparse
import json
import os
from datetime import timedelta


def format_timestamp(seconds):
    td = timedelta(seconds=round(seconds))
    total_seconds = int(td.total_seconds())
    hrs = total_seconds // 3600
    mins = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hrs:02d}:{mins:02d}:{secs:02d},000"


def main(args):
    with open(args.story) as f:
        story = json.load(f)
    with open(args.timing) as f:
        timing = json.load(f)

    start = timing.get("intro_sec", 3)
    scene_dur = timing.get("scene_sec", 4)
    lines = []
    idx = 1
    # intro (title)
    lines.append((1, 0, start, story.get("title", "")))
    cur = start
    for b in story.get("bullets", []):
        text = b.get("text", "")
        lines.append((idx + 1, cur, cur + scene_dur, text))
        cur += scene_dur
        idx += 1

    out = args.output
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        for i, st, en, txt in lines:
            f.write(str(i) + "\n")
            f.write(format_timestamp(st) + " --> " + format_timestamp(en) + "\n")
            f.write(txt + "\n\n")

    print("Wrote SRT:", out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--story", required=True)
    p.add_argument("--timing", default="templates/video_timing.json")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    main(args)
