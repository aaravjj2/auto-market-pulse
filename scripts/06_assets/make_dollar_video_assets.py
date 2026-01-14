#!/usr/bin/env python3
"""Generate story JSON and a cinematic M2 chart + chart_meta for the "Why your dollar is dying" concept.

Creates output in `output/smoke_test/dollar_*`.
"""
from __future__ import annotations
import json
import os
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
from dotenv import load_dotenv

# Prepare output dir
OUTDIR = "auto-market-pulse/output/smoke_test/dollar"
os.makedirs(OUTDIR, exist_ok=True)

# Load API keys from keys.env at repo root (do not print keys)
root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
env_path = os.path.join(root, "keys.env")
if os.path.exists(env_path):
    load_dotenv(env_path)

# Try to fetch M2 series from FRED. Requires FRED_API_KEY in keys.env.
use_fred = True
try:
    from fredapi import Fred
except Exception:
    Fred = None
    use_fred = False

series = None
if Fred is not None:
    fred_key = os.environ.get("FRED_API_KEY") or os.environ.get("FRED_KEY")
    if fred_key:
        try:
            fred = Fred(api_key=fred_key)
            s = fred.get_series("M2SL", start_date="1920-01-01")
            # resample to month end and dropna
            s = s.resample('M').last().dropna()
            series = s
        except Exception:
            series = None

if series is None:
    # fallback: try pandas_datareader
    try:
        import pandas_datareader.data as web
        s = web.DataReader('M2SL', 'fred', start='1920-01-01')
        s = s.resample('M').last().dropna()
        series = s['M2SL'] if isinstance(s, pd.DataFrame) else s
    except Exception:
        series = None

if series is None:
    raise RuntimeError('Could not fetch M2 series. Ensure FRED_API_KEY present in keys.env or internet access available.')

# Normalize series (index to 1.0 at start) for plotting clarity
series_indexed = series / float(series.iloc[0])

# Story JSON per pipeline schema (uses the real M2 symbol)
story = {
    "type": "market_pulse",
    "title": "Why your dollar is dying — " + datetime.now().strftime('%b %d, %Y'),
    "bullets": [
        {"symbol": "M2", "text": "Stop saving cash. It’s bleeding value right now."},
        {"symbol": "M2", "text": "The M2 spike around 2020 erased huge amounts of purchasing power."},
        {"symbol": "M2", "text": "If you want to survive the next decade: Stop saving cash."},
    ],
    "records": [{"symbol": "M2", "note": "FRED M2 series (M2SL)"}],
    "signals": [],
    "summary_tweet": "Stop saving cash — M2 surged in 2020, eroding purchasing power."
}
with open(os.path.join(OUTDIR, "story_dollar.json"), "w") as f:
    json.dump(story, f, indent=2)
print("Wrote story:", os.path.join(OUTDIR, "story_dollar.json"))

# Create cinematic plot (dark theme)
fig, ax = plt.subplots(figsize=(6, 10), dpi=180)
bg = "#0f0f12"
fig.patch.set_facecolor(bg)
ax.set_facecolor(bg)
ax.plot(series_indexed.index, series_indexed.values, color="#00FFAA", linewidth=3, zorder=3)
ax.fill_between(series_indexed.index, series_indexed.values, color="#00FFAA", alpha=0.06)

# highlight 2020-2021 period
mask = (series_indexed.index.year >= 2020) & (series_indexed.index.year <= 2021)
if mask.any():
    start = series_indexed.index[mask][0]
    end = series_indexed.index[mask][-1]
    ax.axvspan(start, end, color="#FF0044", alpha=0.08)

ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_visible(False)
ax.spines['bottom'].set_visible(False)
ax.tick_params(colors="#CCCCCC")
ax.set_title("M2 Money Supply (Indexed)", color="#FFFFFF", fontsize=20, pad=12)
ax.set_ylabel("Indexed level", color="#CCCCCC")
ax.set_xlabel("")
# annotate spike
try:
    peak_idx = series_indexed[mask].idxmax()
    peak_val = float(series_indexed[mask].max())
    ax.annotate("2020 money-printing spike", xy=(peak_idx, peak_val), xytext=(series_indexed.index[10], series_indexed.max()*0.9), color="#FFFFFF", arrowprops=dict(arrowstyle="->", color="#FFFFFF"))
except Exception:
    pass

plt.tight_layout()
img_path = os.path.join(OUTDIR, "scene_01_M2_price.png")
plt.savefig(img_path, facecolor=fig.get_facecolor(), bbox_inches='tight')
plt.close(fig)
print("Wrote chart:", img_path)

# Write chart_meta.json matching pipeline expectations
chart_meta = {
    "scenes": [
        {"scene": 1, "type": "price", "symbol": "M2", "file": img_path}
    ],
    "facts": os.path.join(OUTDIR, "chart_facts.json")
}
with open(os.path.join(OUTDIR, "chart_meta.json"), "w") as f:
    json.dump(chart_meta, f, indent=2)

# facts file
facts = {"source": "FRED M2SL", "created": datetime.now().isoformat()}
with open(os.path.join(OUTDIR, "chart_facts.json"), "w") as f:
    json.dump(facts, f, indent=2)

print("Wrote chart_meta and facts to", OUTDIR)
