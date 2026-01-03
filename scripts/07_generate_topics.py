#!/usr/bin/env python3
"""Generate a ranked list of topic ideas from the latest cache and story.

Outputs `topics.json` and `topics.txt` in the specified outdir.
"""
import argparse
import json
import os
import pandas as pd


def score_topic(row):
    # simple scoring: abs(pct)*2 + vol_mult
    return abs(row.get('pct_change', 0)) * 2 + row.get('vol_mult', 0)


def main(args):
    os.makedirs(args.outdir, exist_ok=True)
    df = pd.read_csv(args.cache, parse_dates=['timestamp'])
    story = {}
    try:
        with open(args.story) as f:
            story = json.load(f)
    except Exception:
        pass

    symbols = sorted(df['symbol'].unique())
    rows = []
    for s in symbols:
        sdf = df[df['symbol'] == s].sort_values('timestamp')
        if len(sdf) < 2:
            continue
        last = float(sdf['close'].iloc[-1])
        prev = float(sdf['close'].iloc[-2])
        pct = (last / prev - 1.0) * 100
        avg30 = float(sdf['volume'].tail(30).mean() or 0)
        vol = float(sdf['volume'].iloc[-1])
        vol_mult = (vol / avg30) if avg30 > 0 else 0
        rows.append({'symbol': s, 'last': last, 'pct_change': pct, 'avg30': avg30, 'vol': vol, 'vol_mult': vol_mult})

    # assemble candidate topics
    candidates = []
    for r in rows:
        # headline topic
        title = f"{r['symbol']}: {r['pct_change']:+.2f}% intraday — closed {r['last']:.2f}"
        score = score_topic(r)
        meta = {'symbol': r['symbol'], 'type': 'headline', 'score': score}
        candidates.append({'title': title, 'score': score, 'meta': meta})

        # volume spike topic
        if r['vol_mult'] > 2.0:
            t2 = f"Vol spike: {r['symbol']} {r['vol_mult']:.1f}x 30d avg"
            candidates.append({'title': t2, 'score': r['vol_mult'] * 5, 'meta': {'symbol': r['symbol'], 'type': 'vol_spike'}})

    # add a general market theme from story title/summary if present
    if story.get('title'):
        candidates.append({'title': f"Market Pulse — {story.get('title')}", 'score': 5, 'meta': {'type': 'market'}})

    # sort and dedupe by title
    seen = set()
    out = []
    for c in sorted(candidates, key=lambda x: x['score'], reverse=True):
        if c['title'] in seen:
            continue
        seen.add(c['title'])
        out.append(c)

    topics_json = os.path.join(args.outdir, 'topics.json')
    with open(topics_json, 'w') as f:
        json.dump(out, f, indent=2)

    topics_txt = os.path.join(args.outdir, 'topics.txt')
    with open(topics_txt, 'w') as f:
        for i, t in enumerate(out, 1):
            f.write(f"{i}. {t['title']} (score={t['score']:.2f})\n")

    print('Wrote topics:', topics_json, topics_txt)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--cache', required=True, help='cache CSV path')
    p.add_argument('--story', required=False, help='story JSON path')
    p.add_argument('--outdir', required=True, help='output dir for topics')
    args = p.parse_args()
    main(args)
