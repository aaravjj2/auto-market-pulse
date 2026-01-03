#!/usr/bin/env python3
"""Detect market signals from cached CSV data.

Produces a JSON file with structured signals and simple narrative templates.
"""
import argparse
import json
import os
import pandas as pd
import importlib.util
from pathlib import Path


def rolling_ma(series, window):
    return series.rolling(window=window, min_periods=1).mean()


def detect_for_ticker(df, ticker, spy_df=None):
    out = {"ticker": ticker, "signals": []}
    s = df.copy()
    s["ma20"] = rolling_ma(s["close"], 20)
    s["ma50"] = rolling_ma(s["close"], 50)
    s["vol20"] = rolling_ma(s["volume"], 20)

    if len(s) < 3:
        return out

    # Moving average crossover (recent)
    if s["ma20"].iat[-1] > s["ma50"].iat[-1] and s["ma20"].iat[-2] <= s["ma50"].iat[-2]:
        out["signals"].append({
            "type": "ma_crossover",
            "dir": "bullish",
            "narrative": f"Signal Alert — {ticker} Momentum Flip!"});
    elif s["ma20"].iat[-1] < s["ma50"].iat[-1] and s["ma20"].iat[-2] >= s["ma50"].iat[-2]:
        out["signals"].append({
            "type": "ma_crossover",
            "dir": "bearish",
            "narrative": f"Signal Alert — {ticker} Momentum Flip (bearish)!"});

    # Volume spike (last bar vs 20-day avg)
    vol_ratio = float(s["volume"].iat[-1] / max(1, s["vol20"].iat[-1]))
    if vol_ratio >= 2.0:
        out["signals"].append({
            "type": "volume_spike",
            "vol_ratio": round(vol_ratio, 2),
            "narrative": f"Volume spike — {ticker} volume is {vol_ratio:.1f}x its 20-day average."})

    # Short-term divergence vs SPY (if provided)
    if spy_df is not None and "close" in spy_df.columns and "close" in s.columns:
        # compute 5-day returns
        rtn = s["close"].pct_change(5).iat[-1]
        spy_rtn = spy_df["close"].pct_change(5).iat[-1] if len(spy_df) >= 5 else 0.0
        diff = float((rtn - spy_rtn) * 100)
        if abs(diff) >= 1.0:
            out["signals"].append({
                "type": "divergence",
                "diff_pct": round(diff, 2),
                "narrative": f"{ticker} has diverged from SPY by {diff:.2f}% this week."})

    # Try to enrich with StockTwits sentiment if available
    try:
        mod_path = Path(__file__).parent / "stocktwits_sentiment.py"
        if mod_path.exists():
            spec = importlib.util.spec_from_file_location("st_sent", str(mod_path))
            st_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(st_mod)
            sent = st_mod.get_sentiment(ticker)
            out["sentiment"] = sent
            if sent.get("total", 0) >= 5 and sent.get("bull", 0) - sent.get("bear", 0) >= 3:
                out["signals"].append({
                    "type": "sentiment_bull",
                    "narrative": f"Social buzz on {ticker} is unusually high (Bullish mentions > Bearish)."})
            elif sent.get("total", 0) >= 5 and sent.get("bear", 0) - sent.get("bull", 0) >= 3:
                out["signals"].append({
                    "type": "sentiment_bear",
                    "narrative": f"Social buzz on {ticker} is leaning bearish."})
    except Exception:
        pass

    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cache", required=True, help="path to CSV cache directory or single csv file")
    p.add_argument("--outdir", default="output/signals", help="output directory for signals.json")
    p.add_argument("--spy", default="SPY", help="ticker symbol for market benchmark in cache (filename or column) if available")
    args = p.parse_args()

    cache = args.cache
    os.makedirs(args.outdir, exist_ok=True)

    # Support either a directory of CSVs or a single CSV file
    tickers = {}
    if os.path.isdir(cache):
        for fn in os.listdir(cache):
            if fn.lower().endswith(".csv"):
                t = os.path.splitext(fn)[0]
                try:
                    df = pd.read_csv(os.path.join(cache, fn), parse_dates=["date"]).sort_values("date")
                    tickers[t] = df
                except Exception:
                    continue
    else:
        # single CSV; assume contains a ticker column
        df_all = pd.read_csv(cache, parse_dates=["date"]) if os.path.exists(cache) else pd.DataFrame()
        if "ticker" in df_all.columns:
            for t, g in df_all.groupby("ticker"):
                tickers[t] = g.sort_values("date")
        else:
            # place under filename
            t = os.path.splitext(os.path.basename(cache))[0]
            tickers[t] = df_all.sort_values("date")

    spy_df = tickers.get(args.spy)

    results = {"generated_at": pd.Timestamp.now().isoformat(), "signals": []}
    for t, df in tickers.items():
        if df.empty:
            continue
        sig = detect_for_ticker(df, t, spy_df=spy_df)
        if sig.get("signals"):
            results["signals"].append(sig)

    out_path = os.path.join(args.outdir, "signals.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print("Wrote signals:", out_path)


if __name__ == "__main__":
    main()
