#!/usr/bin/env python3
"""Generate SEO-friendly titles and thumbnail text from signals.json"""
import argparse
import json
import os


TITLE_TEMPLATES = [
    "📊 {headline} — Here’s What That Means (30s)",
    "⚠️ {headline} — Quick Breakdown",
    "🔥 {headline} — Short Summary",
]


def choose_headline(signal):
    # Prefer MA crossover > volume > divergence
    for s in signal.get("signals", []):
        if s["type"] == "ma_crossover":
            return s.get("narrative")
    for s in signal.get("signals", []):
        if s["type"] == "volume_spike":
            return s.get("narrative")
    for s in signal.get("signals", []):
        if s["type"] == "divergence":
            return s.get("narrative")
    return f"Market note — {signal.get('ticker')}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--signals", required=True, help="path to signals.json")
    p.add_argument("--out", default="output/signals/title.json", help="output file for title+thumb text")
    args = p.parse_args()

    with open(args.signals) as f:
        data = json.load(f)

    out = {"candidates": []}
    for sig in data.get("signals", []):
        headline = choose_headline(sig)
        template = TITLE_TEMPLATES[0]
        title = template.format(headline=headline)
        thumb = {
            "line1": headline.split(" — ")[0],
            "line2": f"{sig.get('ticker')} • {len(sig.get('signals', []))} signals",
        }
        out["candidates"].append({"ticker": sig.get("ticker"), "title": title, "thumb": thumb})

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print("Wrote titles:", args.out)


if __name__ == "__main__":
    main()
