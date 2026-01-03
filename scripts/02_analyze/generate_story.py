#!/usr/bin/env python3
"""Generate a deterministic story JSON from cached price CSVs.

Input: cache CSV containing rows with timestamp,symbol,open,high,low,close,volume
Output: story JSON with bullets and summary_tweet
"""
import argparse
import json
import os
from datetime import datetime

import numpy as np
import pandas as pd
import importlib.util
import sys
from pathlib import Path


def load_cache(path):
    df = pd.read_csv(path, parse_dates=["timestamp"])
    return df


def pct_change_series(series):
    if len(series) < 2:
        return 0.0
    return (series.iloc[-1] - series.iloc[0]) / series.iloc[0] * 100.0


def slope(series):
    # simple linear slope (percent per point)
    if len(series) < 2:
        return 0.0
    x = np.arange(len(series))
    y = np.array(series)
    m, _ = np.polyfit(x, y, 1)
    return float(m)


def compute_metrics(df, symbol, days=5):
    sdf = df[df["symbol"] == symbol].sort_values("timestamp")
    if sdf.empty:
        return None
    recent = sdf.tail(days)
    pct = pct_change_series(recent["close"]) if len(recent) >= 2 else 0.0
    sl = slope(recent["close"]) if len(recent) >= 2 else 0.0
    # 30-day momentum approx
    mom = 0.0
    if len(sdf) >= 30:
        mom = (sdf["close"].iloc[-1] - sdf["close"].iloc[-30]) / sdf["close"].iloc[-30] * 100.0
    # volume spike: compare last to avg of previous days
    vol_avg = sdf["volume"].iloc[-21:-1].mean() if len(sdf) > 2 else sdf["volume"].mean()
    last_vol = int(sdf["volume"].iloc[-1])
    vol_mult = float(last_vol / vol_avg) if vol_avg and not np.isnan(vol_avg) else 1.0

    return {
        "symbol": symbol,
        "close": float(sdf["close"].iloc[-1]),
        "pct_change": round(float(pct), 4),
        "slope": round(float(sl), 6),
        "momentum_30d": round(float(mom), 4),
        "volume": last_vol,
        "vol_mult": round(float(vol_mult), 2),
    }


def generate_story(df, symbols, days=5):
    records = []
    for sym in symbols:
        m = compute_metrics(df, sym, days=days)
        if m:
            records.append(m)

    # relative perf vs SPY
    spy = next((r for r in records if r["symbol"] == "SPY"), None)

    bullets = []
    for r in records:
        text = f"{r['symbol']} closed {r['pct_change']:+.2f}% at ${r['close']:.2f}"
        if r["vol_mult"] > 1.5:
            text += f" — unusual volume: {r['vol_mult']:.1f}x avg"
        if spy and r["symbol"] != "SPY":
            rel = r["pct_change"] - spy["pct_change"]
            text += f" (vs SPY {rel:+.2f}%)"
        # attach symbol for downstream rendering
        bullets.append({"symbol": r["symbol"], "text": text})

    title = f"Market Pulse — {datetime.now().strftime('%b %d, %Y')}"
    summary = " | ".join([f"{r['symbol']} {r['pct_change']:+.2f}%" for r in records[:4]])

    story = {
        "type": "market_pulse",
        "title": title,
        "bullets": bullets,
        "records": records,
        "signals": [],
        "summary_tweet": f"{summary} — snapshot",
    }
    # Attempt to enrich with signals from scripts/08_signals/detect_signals.py
    try:
        mod_path = Path(__file__).parent.parent / "scripts" / "08_signals" / "detect_signals.py"
        if mod_path.exists():
            spec = importlib.util.spec_from_file_location("detect_signals", str(mod_path))
            ds = importlib.util.module_from_spec(spec)
            sys.modules["detect_signals"] = ds
            spec.loader.exec_module(ds)
            # build per-symbol DataFrame and call detect_for_ticker
            for r in records:
                sym = r["symbol"]
                sdf = df[df["symbol"] == sym].sort_values("timestamp")
                try:
                    sig = ds.detect_for_ticker(sdf.rename(columns={"timestamp": "date", "close": "close", "volume": "volume"}), sym, spy_df=None)
                    if sig and sig.get("signals"):
                        story["signals"].append(sig)
                        # attach signals to bullet if matches
                        for b in story["bullets"]:
                            if b.get("symbol") == sym:
                                b.setdefault("signals", []).extend(sig.get("signals", []))
                except Exception:
                    continue
    except Exception:
        # best-effort only; do not fail story generation
        pass

    return story


def main(args):
    df = load_cache(args.cache)
    symbols = args.symbols.split(",") if args.symbols else sorted(df["symbol"].unique())
    story = generate_story(df, symbols, days=args.days)
    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(story, f, indent=2)
    print("Wrote story:", args.output)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--cache", required=True, help="path to cache CSV")
    p.add_argument("--output", required=True, help="output story JSON")
    p.add_argument("--symbols", help="comma-separated symbols (optional)")
    p.add_argument("--days", type=int, default=5, help="lookback days for pct change")
    args = p.parse_args()
    main(args)
