#!/usr/bin/env python3
"""Generate ASS subtitle file from story JSON and timing with polished style."""
import argparse
import json
import os
from datetime import timedelta


def fmt_ass_time(seconds):
    # ASS uses H:MM:SS.ss (centiseconds)
    cs = int(round(seconds * 100))
    s = cs // 100
    cs_rem = cs % 100
    hrs = s // 3600
    mins = (s % 3600) // 60
    secs = s % 60
    return f"{hrs}:{mins:02d}:{secs:02d}.{cs_rem:02d}"


def main(args):
    with open(args.story) as f:
        story = json.load(f)
    with open(args.timing) as f:
        timing = json.load(f)

    events = []
    cur = 0.0
    intro = timing.get("intro_sec", 3)
    events.append((0.0, intro, story.get("title", "Market Pulse")))
    cur = intro
    scene = timing.get("scene_sec", 4)
    for b in story.get("bullets", []):
        text = b.get("text", "")
        # shorten long parenthetical parts for cleaner lines
        events.append((cur, cur + scene, text))
        cur += scene
    outro = timing.get("outro_sec", 2)
    events.append((cur, cur + outro, "End — Educational content. Not financial advice."))

    out = []
    out.append("[Script Info]")
    out.append("Title: auto-market-pulse subtitles")
    out.append("ScriptType: v4.00+")
    out.append("")
    out.append("[V4+ Styles]")
    out.append("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
    # small, bold, outlined, shadowed, bottom-center (2)
    out.append("Style: Default,DejaVu Sans,44,&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,2,1,2,30,30,80,1")
    out.append("")
    out.append("[Events]")
    out.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")

    for s, e, txt in events:
        start = fmt_ass_time(s)
        end = fmt_ass_time(e)
        # simple wrap: replace long commas with line breaks for readability
        if len(txt) > 40:
            # attempt to split at comma or dash
            if "," in txt:
                txt = txt.replace(",", "\\N,")
            elif " — " in txt:
                txt = txt.replace(" — ", "\\N— ")
            else:
                # break at nearest space around mid
                mid = len(txt) // 2
                sp = txt.rfind(' ', 0, mid)
                if sp != -1:
                    txt = txt[:sp] + "\\N" + txt[sp+1:]
        # small fade in/out using {
        text_line = f"Dialogue: 0,{start},{end},Default,,0,0,0,,{{\\fad(150,150)}}{txt}"
        out.append(text_line)

    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
    with open(args.output, 'w') as f:
        f.write("\n".join(out))
    print("Wrote ASS:", args.output)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--story', required=True)
    p.add_argument('--timing', default='templates/video_timing.json')
    p.add_argument('--output', required=True)
    args = p.parse_args()
    main(args)
