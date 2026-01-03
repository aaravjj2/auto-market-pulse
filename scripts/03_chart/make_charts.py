#!/usr/bin/env python3
"""Generate mobile-readable charts (PNG) for story scenes.

Creates price candlestick PNGs, a small pct-change image, and a volume image.
Saves metadata mapping charts to scene order.
"""
import argparse
import json
import os
from datetime import datetime

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import numpy as np


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def make_candlestick(df, symbol, outpath, figsize=(4.8, 8.533)):
    dfc = df.copy()
    dfc.index = pd.DatetimeIndex(dfc["timestamp"])
    dfc = dfc[["open", "high", "low", "close", "volume"]]
    # mobile-friendly tall layout and cleaner style
    style = mpf.make_mpf_style(base_mpf_style="yahoo", rc={"font.size": 12})
    # add a 20-period moving average and volume panel
    try:
        fig, axes = mpf.plot(dfc, type="candle", style=style, volume=True, mav=(20,), returnfig=True, figsize=figsize, show_nontrading=False)
        # annotate a brief fact box: latest close and percent change
        try:
            last = float(dfc['close'].iloc[-1])
            prev = float(dfc['close'].iloc[-2])
            pct = (last / prev - 1.0) * 100
            fact = f"{symbol} {last:.2f} ({pct:+.2f}%)"
        except Exception:
            fact = symbol
        fig.text(0.5, 0.96, fact, ha='center', va='top', fontsize=18, color='white', weight='bold', bbox=dict(facecolor='black', alpha=0.6, pad=6))
        # a small facts line with highest-volume day info
        try:
            idxmax = dfc['volume'].idxmax()
            vmax = dfc['volume'].max()
            vfact = f"Highest vol: {idxmax.date()} ({int(vmax):,})"
            fig.text(0.5, 0.92, vfact, ha='center', va='top', fontsize=12, color='white', bbox=dict(facecolor='black', alpha=0.45, pad=4))
        except Exception:
            pass
        fig.savefig(outpath, dpi=150, bbox_inches='tight')
        plt.close(fig)
    except Exception:
        # fallback to simple mplfinance save
        mpf.plot(dfc, type="candle", style=style, volume=False, show_nontrading=False, savefig=dict(fname=outpath, dpi=150), figsize=figsize)

    # Post-processing annotations: mark last MA crossover and volume spikes
    try:
        # compute moving averages directly
        ma20 = dfc['close'].rolling(window=20, min_periods=1).mean()
        ma50 = dfc['close'].rolling(window=50, min_periods=1).mean()
        sig = np.sign(ma20 - ma50)
        cross = np.where(np.diff(sig) != 0)[0]
        if len(cross) > 0:
            last_idx = cross[-1] + 1
            dt = dfc.index[last_idx]
            price = dfc['close'].iloc[last_idx]
            ax_price = axes[0]
            ax_price.annotate('MA crossover', xy=(dt, price), xytext=(dt, price * 1.02), arrowprops=dict(facecolor='yellow', shrink=0.05), color='yellow', fontsize=10, weight='bold')
            # vertical line on both axes to highlight event
            for ax in axes:
                try:
                    ax.axvline(dt, color='yellow', linestyle='--', linewidth=1, alpha=0.6)
                except Exception:
                    pass

        # volume spikes: mark days where volume > 2x 20-day avg
        vol20 = dfc['volume'].rolling(window=20, min_periods=1).mean()
        spikes = dfc.index[(dfc['volume'] > 2 * vol20)]
        if len(spikes) > 0:
            for sp in spikes[-3:]:
                for ax in axes[-1:]:
                    try:
                        ax.axvline(sp, color='red', linestyle=':', linewidth=1.2, alpha=0.7)
                    except Exception:
                        pass
        # re-save the annotated figure (overwrite)
        fig.savefig(outpath, dpi=150, bbox_inches='tight')
        plt.close(fig)
    except Exception:
        # non-fatal
        pass


def make_pct_chart(df, symbol, outpath, days=5, figsize=(4.8, 2.5)):
    sdf = df[df["symbol"] == symbol].sort_values("timestamp").tail(days)
    if sdf.empty:
        return
    pct = (sdf["close"].pct_change() * 100).fillna(0)
    plt.figure(figsize=figsize)
    plt.plot(sdf["timestamp"], pct, marker="o", linewidth=2, color="#FF7F0E")
    plt.fill_between(sdf["timestamp"], 0, pct, alpha=0.05, color="#FF7F0E")
    plt.title(f"{symbol} % change (last {days} days)")
    plt.ylabel("%")
    plt.xticks(rotation=15)
    plt.grid(True, alpha=0.25)
    plt.tight_layout()
    plt.savefig(outpath, dpi=150)
    plt.close()


def make_volume_chart(df, symbol, outpath, days=30, figsize=(4.8, 2.5)):
    sdf = df[df["symbol"] == symbol].sort_values("timestamp").tail(days)
    if sdf.empty:
        return
    plt.figure(figsize=figsize)
    plt.bar(sdf["timestamp"], sdf["volume"], color="#4C72B0")
    # highlight spikes
    avg = sdf["volume"].mean()
    plt.axhline(avg, color='gray', linestyle='--', linewidth=1, alpha=0.6)
    plt.title(f"{symbol} Volume (last {days} days)")
    plt.xticks(rotation=15)
    plt.tight_layout()
    plt.savefig(outpath, dpi=150)
    plt.close()


def make_top_movers(df, outpath, top_n=5, figsize=(4.8, 2.0)):
    # compute last-close percent change for each symbol
    rows = []
    for s in sorted(df['symbol'].unique()):
        sdf = df[df['symbol'] == s].sort_values('timestamp')
        if len(sdf) < 2:
            continue
        last = float(sdf['close'].iloc[-1])
        prev = float(sdf['close'].iloc[-2])
        pct = (last / prev - 1.0) * 100
        avgvol = int(sdf['volume'].tail(30).mean() or 0)
        rows.append((s, last, pct, avgvol))
    if not rows:
        return
    rows = sorted(rows, key=lambda r: abs(r[2]), reverse=True)[:top_n]
    # render a compact table
    fig, ax = plt.subplots(figsize=figsize)
    ax.axis('off')
    collabels = ['Symbol', 'Close', '%', 'AvgVol']
    table_vals = [[r[0], f"{r[1]:.2f}", f"{r[2]:+.2f}%", f"{r[3]:,}"] for r in rows]
    table = ax.table(cellText=table_vals, colLabels=collabels, cellLoc='center', loc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.2)
    fig.tight_layout()
    fig.savefig(outpath, dpi=150, bbox_inches='tight')
    plt.close(fig)


def main(args):
    ensure_dir(args.outdir)
    df = pd.read_csv(args.cache, parse_dates=["timestamp"]) if args.cache else None
    with open(args.story) as f:
        story = json.load(f)
    # optional plotly export
    do_plotly = getattr(args, 'plotly', False)
    plotly_files = []

    # choose symbols: SPY, GLD, SLV, plus first other if available
    symbols = ["SPY", "GLD", "SLV"]
    if df is not None:
        extra = [s for s in sorted(df["symbol"].unique()) if s not in symbols]
        if extra:
            symbols.append(extra[0])

    chart_map = {"scenes": []}
    scene_idx = 1
    available = list(df["symbol"].unique()) if df is not None else symbols
    for sym in [s for s in symbols if s in available][:4]:
        price_out = os.path.join(args.outdir, f"scene_{scene_idx:02d}_{sym}_price.png")
        make_candlestick(df[df["symbol"] == sym], sym, price_out)
        chart_map["scenes"].append({"scene": scene_idx, "type": "price", "symbol": sym, "file": price_out})
        scene_idx += 1

        pct_out = os.path.join(args.outdir, f"scene_{scene_idx:02d}_{sym}_pct.png")
        make_pct_chart(df, sym, pct_out)
        chart_map["scenes"].append({"scene": scene_idx, "type": "pct", "symbol": sym, "file": pct_out})
        scene_idx += 1

        vol_out = os.path.join(args.outdir, f"scene_{scene_idx:02d}_{sym}_vol.png")
        make_volume_chart(df, sym, vol_out)
        chart_map["scenes"].append({"scene": scene_idx, "type": "volume", "symbol": sym, "file": vol_out})
        scene_idx += 1
        # optional Plotly interactive export
        if do_plotly:
            try:
                import plotly.graph_objects as go
                import plotly.io as pio
                sdf = df[df['symbol'] == sym].sort_values('timestamp')
                if not sdf.empty:
                    fig = go.Figure()
                    fig.add_trace(go.Candlestick(x=sdf['timestamp'], open=sdf['open'], high=sdf['high'], low=sdf['low'], close=sdf['close'], name=f'{sym}'))
                    fig.update_layout(title=f"{sym} price", xaxis_title='time', yaxis_title='price')
                    pth = os.path.join(args.outdir, f"scene_{scene_idx-3:02d}_{sym}_interactive.html")
                    pio.write_html(fig, file=pth, auto_open=False)
                    plotly_files.append(pth)
            except Exception:
                pass

    meta_out = os.path.join(args.outdir, "chart_meta.json")
    with open(meta_out, "w") as f:
        json.dump(chart_map, f, indent=2)

    # top movers summary image
    top_out = os.path.join(args.outdir, "top_movers.png")
    try:
        make_top_movers(df, top_out)
        chart_map['top_movers'] = top_out
    except Exception:
        pass

    # write a simple facts.json with a few computed facts
    facts = {}
    try:
        overall = df.groupby('symbol').apply(lambda g: float(g['close'].iloc[-1]))
        facts['price_snapshot'] = overall.to_dict()
    except Exception:
        facts['price_snapshot'] = {}
    facts_out = os.path.join(args.outdir, 'chart_facts.json')
    with open(facts_out, 'w') as f:
        json.dump(facts, f, indent=2)
    chart_map['facts'] = facts_out
    if do_plotly and plotly_files:
        chart_map['plotly'] = plotly_files

    print("Wrote charts to", args.outdir)
    print("Meta:", meta_out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--story", required=True, help="story JSON path")
    p.add_argument("--cache", required=True, help="cache CSV path")
    p.add_argument("--outdir", required=True, help="output directory for charts")
    p.add_argument("--plotly", action="store_true", help="export interactive Plotly HTML charts")
    args = p.parse_args()
    main(args)
