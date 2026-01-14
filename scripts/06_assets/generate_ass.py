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
    events.append({"start": 0.0, "end": intro, "text": story.get("title", "Market Pulse")})
    cur = intro
    scene = timing.get("scene_sec", 4)
    # bullets may include symbol and signals
    for b in story.get("bullets", []):
        text = b.get("text", "")
        events.append({"start": cur, "end": cur + scene, "text": text, "bullet": b})
        cur += scene
    outro = timing.get("outro_sec", 2)
    events.append({"start": cur, "end": cur + outro, "text": "End — Educational content. Not financial advice."})

    out = []
    out.append("[Script Info]")
    out.append("Title: auto-market-pulse subtitles")
    out.append("ScriptType: v4.00+")
    out.append("")
    out.append("[V4+ Styles]")
    out.append("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
    # small, bold, outlined, shadowed, bottom-center (2)
    out.append("Style: Default,DejaVu Sans,44,&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,2,1,2,30,30,80,1")
    # Alert/badge style (bold, slightly smaller, top-right)
    out.append("Style: Alert,DejaVu Sans,36,&H000000FF,&H00FFFFFF,&H00000000,&H80FF0000,1,0,0,0,100,100,0,0,1,2,1,8,30,30,30,1")
    out.append("")
    out.append("[Events]")
    out.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")

    for ev in events:
        s = ev["start"]
        e = ev["end"]
        txt = ev["text"]
        start = fmt_ass_time(s)
        end = fmt_ass_time(e)
        # simple wrap: replace long commas with line breaks for readability
        if len(txt) > 40:
            if "," in txt:
                txt = txt.replace(",", "\\N,")
            elif " — " in txt:
                txt = txt.replace(" — ", "\\N— ")
            else:
                mid = len(txt) // 2
                sp = txt.rfind(' ', 0, mid)
                if sp != -1:
                    txt = txt[:sp] + "\\N" + txt[sp+1:]
        # main caption
        text_line = f"Dialogue: 0,{start},{end},Default,,0,0,0,,{{\\fad(150,150)}}{txt}"
        out.append(text_line)

        # if this event has signals, add alert overlays (short badges)
        b = ev.get("bullet")
        if b and b.get("signals"):
            # show each signal as a short badge at top-right for first 1.8s of the scene
            badge_dur = min(1.8, e - s)
            badge_start = s
            badge_end = s + badge_dur
            bs = fmt_ass_time(badge_start)
            be = fmt_ass_time(badge_end)
            for sig in b.get("signals", [])[:2]:
                badge_text = sig.get("narrative", sig.get("type", "Signal"))
                # sanitize commas/newlines
                badge_text = badge_text.replace("\n", " ")
                badge_line = f"Dialogue: 0,{bs},{be},Alert,,0,0,0,,{{\\an9\\pos(1180,60)\\bord3\\shad1}}{badge_text}"
                out.append(badge_line)

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
