#!/usr/bin/env python3
"""Lightweight StockTwits sentiment scraper with simple file cache.

Returns counts of bullish vs bearish mentions for a ticker using public StockTwits stream.
Uses a simple JSON cache under `.cache/stocktwits` with TTL (default 300s).
"""
import requests
import time
import json
from pathlib import Path


CACHE_DIR = Path('.cache') / 'stocktwits'
CACHE_DIR.mkdir(parents=True, exist_ok=True)
TTL = 300


def _cache_path(ticker):
    return CACHE_DIR / f"{ticker.upper()}.json"


def get_sentiment(ticker, max_msgs=50):
    p = _cache_path(ticker)
    try:
        if p.exists():
            j = json.loads(p.read_text())
            if time.time() - j.get('_ts', 0) < TTL:
                return j.get('payload', {'bull': 0, 'bear': 0, 'total': 0})
    except Exception:
        pass

    url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
    try:
        r = requests.get(url, timeout=6)
        r.raise_for_status()
        data = r.json()
        msgs = data.get("messages", [])[:max_msgs]
        bull = 0
        bear = 0
        for m in msgs:
            s = m.get("entities", {}).get("sentiment")
            if s and s.get("basic"):
                b = s.get("basic").lower()
                if "bull" in b:
                    bull += 1
                elif "bear" in b:
                    bear += 1
        payload = {"bull": bull, "bear": bear, "total": len(msgs)}
        try:
            p.write_text(json.dumps({'_ts': time.time(), 'payload': payload}))
        except Exception:
            pass
        return payload
    except Exception:
        return {"bull": 0, "bear": 0, "total": 0}


if __name__ == "__main__":
    print(get_sentiment("AAPL"))
