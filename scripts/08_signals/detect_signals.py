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
import math

# load config if present
CONFIG_PATH = Path(__file__).parent / "signals_config.json"
if CONFIG_PATH.exists():
    try:
        with open(CONFIG_PATH) as cf:
            CFG = json.load(cf)
    except Exception:
        CFG = {}
else:
    CFG = {}


def rolling_ma(series, window):
    return series.rolling(window=window, min_periods=1).mean()


def detect_for_ticker(df, ticker, spy_df=None):
    out = {"ticker": ticker, "signals": []}
    s = df.copy()
    short = int(CFG.get("ma_short", 20))
    long = int(CFG.get("ma_long", 50))
    s["ma_short"] = rolling_ma(s["close"], short)
    s["ma_long"] = rolling_ma(s["close"], long)
    s["vol20"] = rolling_ma(s["volume"], 20)

    if len(s) < 3:
        return out

    # Moving average crossover (recent)
    # MA crossover using configured windows
    try:
        cur_short = s[f"ma_short"].iat[-1]
        prev_short = s[f"ma_short"].iat[-2]
        cur_long = s[f"ma_long"].iat[-1]
        prev_long = s[f"ma_long"].iat[-2]
        if cur_short > cur_long and prev_short <= prev_long:
            out["signals"].append({
                "type": "ma_crossover",
                "dir": "bullish",
                "narrative": f"Signal Alert — {ticker} Momentum Flip!"})
        elif cur_short < cur_long and prev_short >= prev_long:
            out["signals"].append({
                "type": "ma_crossover",
                "dir": "bearish",
                "narrative": f"Signal Alert — {ticker} Momentum Flip (bearish)!"})
    except Exception:
        pass

    # Volume spike (last bar vs 20-day avg)
    vol_ratio = float(s["volume"].iat[-1] / max(1, s["vol20"].iat[-1]))
    vol_thresh = float(CFG.get("volume_spike_multiplier", 2.0))
    if not math.isfinite(vol_ratio):
        vol_ratio = 1.0
    if vol_ratio >= vol_thresh:
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
            min_msgs = int(CFG.get("volume_min_messages_for_sentiment", 5))
            delta_th = int(CFG.get("sentiment_delta_threshold", 3))
            if sent.get("total", 0) >= min_msgs and sent.get("bull", 0) - sent.get("bear", 0) >= delta_th:
                out["signals"].append({
                    "type": "sentiment_bull",
                    "narrative": f"Social buzz on {ticker} is unusually high (Bullish mentions > Bearish)."})
            elif sent.get("total", 0) >= min_msgs and sent.get("bear", 0) - sent.get("bull", 0) >= delta_th:
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
                    df = pd.read_csv(os.path.join(cache, fn))
                    # support either 'date' or 'timestamp' column names
                    if "date" not in df.columns and "timestamp" in df.columns:
                        df["date"] = pd.to_datetime(df["timestamp"])
                    elif "date" in df.columns:
                        df["date"] = pd.to_datetime(df["date"])
                    tickers[t] = df.sort_values("date")
                except Exception:
                    continue
    else:
        # single CSV; assume contains a ticker column
        df_all = pd.read_csv(cache) if os.path.exists(cache) else pd.DataFrame()
        if "ticker" in df_all.columns:
            for t, g in df_all.groupby("ticker"):
                gg = g.copy()
                if "date" not in gg.columns and "timestamp" in gg.columns:
                    gg["date"] = pd.to_datetime(gg["timestamp"])
                elif "date" in gg.columns:
                    gg["date"] = pd.to_datetime(gg["date"])
                tickers[t] = gg.sort_values("date")
        else:
            # place under filename
            t = os.path.splitext(os.path.basename(cache))[0]
            dfc = df_all.copy()
            if "date" not in dfc.columns and "timestamp" in dfc.columns:
                dfc["date"] = pd.to_datetime(dfc["timestamp"])
            elif "date" in dfc.columns:
                dfc["date"] = pd.to_datetime(dfc["date"])
            tickers[t] = dfc.sort_values("date")

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
