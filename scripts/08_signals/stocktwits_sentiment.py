#!/usr/bin/env python3
"""Lightweight StockTwits sentiment scraper.

Returns counts of bullish vs bearish mentions for a ticker using public StockTwits stream.
This is a best-effort scraper — the API is public but rate-limited.
"""
import requests


def get_sentiment(ticker, max_msgs=50):
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
        return {"bull": bull, "bear": bear, "total": len(msgs)}
    except Exception:
        return {"bull": 0, "bear": 0, "total": 0}


if __name__ == "__main__":
    print(get_sentiment("AAPL"))
