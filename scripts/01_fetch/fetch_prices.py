#!/usr/bin/env python3
"""Fetch latest prices for tickers using yfinance.

Saves raw JSON snapshots and a normalized CSV cache per day.
"""
import argparse
import json
import os
import time
from datetime import datetime

import pandas as pd
import yfinance as yf


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def now_et_iso():
    # Use local time as proxy; users should ensure machine is set appropriately.
    return datetime.now().astimezone().isoformat()


def fetch_ticker_history(ticker, period="30d", interval="1d", retries=3):
    backoff = 1
    for attempt in range(retries):
        try:
            t = yf.Ticker(ticker)
            df = t.history(period=period, interval=interval, auto_adjust=False)
            if df is None or df.empty:
                raise ValueError("empty dataframe")
            df = df.reset_index()
            return df
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(backoff)
                backoff *= 2
                continue
            raise


def main(args):
    ensure_dir("data/raw")
    ensure_dir("data/cache")

    # load tickers
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
    else:
        with open("config/tickers.json") as f:
            cfg = json.load(f)
            tickers = cfg.get("tickers", [])

    request_ts = now_et_iso()
    raw_records = []
    rows = []

    for sym in sorted(tickers):
        df = fetch_ticker_history(sym, period=args.period)
        # save raw per-symbol minimal JSON for provenance
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        pct_change = (latest["Close"] - prev["Close"]) / prev["Close"] * 100 if prev["Close"] else 0.0

        raw = {
            "timestamp": request_ts,
            "symbol": sym,
            "close": float(latest["Close"]),
            "pct_change": round(float(pct_change), 4),
            "volume": int(latest.get("Volume", 0)),
            "source": "yfinance",
        }
        raw_records.append(raw)

        # normalized rows for cache CSV (all dates in history)
        for _, r in df.iterrows():
            rows.append(
                {
                    "timestamp": r["Date"].isoformat(),
                    "symbol": sym,
                    "open": float(r.get("Open", "nan")),
                    "high": float(r.get("High", "nan")),
                    "low": float(r.get("Low", "nan")),
                    "close": float(r.get("Close", "nan")),
                    "volume": int(r.get("Volume", 0) or 0),
                }
            )

    # save raw snapshot
    raw_fname = datetime.now().strftime("data/raw/%Y%m%d_%H%M%S_tickers.json")
    with open(raw_fname, "w") as f:
        json.dump({"request_ts": request_ts, "records": raw_records}, f, indent=2)

    # save normalized cache per day
    cache_fname = datetime.now().strftime("data/cache/%Y%m%d_tickers.csv")
    df_cache = pd.DataFrame(rows)
    df_cache.to_csv(cache_fname, index=False)

    print("Saved raw:", raw_fname)
    print("Saved cache:", cache_fname)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--now", action="store_true", help="fetch for now")
    parser.add_argument("--tickers", help="comma-separated tickers override")
    parser.add_argument("--period", default="30d", help="yfinance period (default 30d)")
    args = parser.parse_args()
    main(args)
