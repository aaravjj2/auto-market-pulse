#!/usr/bin/env python3
"""Generate mobile-readable charts using Manim with transparent background.

Creates price candlestick animations, percentage change charts, and volume charts
with transparent background for compositing over background videos.

Output: .mov files (ProRes 4444) or PNG image sequences with alpha channel.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

try:
    from manim import (
        config,
        Scene,
        Rectangle,
        Text,
        VGroup,
        Line,
        Axes,
        ValueTracker,
        Create,
        FadeIn,
        WHITE,
        GREEN,
        RED,
        BLUE,
        ORANGE,
        UP,
        DOWN,
    )
    # For transparent background in Manim
    # Use None or config.background_color = None to get transparency
    MANIM_AVAILABLE = True
except ImportError:
    MANIM_AVAILABLE = False
    print("Warning: Manim not available. Install with: pip install manim", file=sys.stderr)


# Module-level data storage for scenes (set before each render)
_current_scene_data = {}

def configure_manim_transparent(output_format: str = "mov"):
    """Configure Manim for transparent background rendering.
    
    Args:
        output_format: Either "mov" (ProRes 4444) or "png" (image sequence)
    """
    if not MANIM_AVAILABLE:
        return
    
    # 9:16 vertical 1080x1920 format
    config.pixel_width = 1080
    config.pixel_height = 1920
    config.frame_rate = 30
    
    # Set background to TRANSPARENT (None = transparent in Manim)
    # This enables alpha channel output
    config.background_color = None
    
    # Enable transparent rendering
    config.transparent = True
    
    # Configure output format
    if output_format.lower() == "png":
        # PNG sequence with alpha
        config.format = "png"
    # mov format is default and supports transparency with ProRes 4444 codec


class CandlestickChartScene(Scene):
    """Manim scene for candlestick price chart with transparent background."""
    
    def construct(self):
        # Get data from module-level store
        if not _current_scene_data:
            self.wait(1)
            return
        df = _current_scene_data.get('df')
        symbol = _current_scene_data.get('symbol')
        if df is None or symbol is None:
            self.wait(1)
            return
        
        df = df.copy()
        df.index = pd.DatetimeIndex(df["timestamp"])
        duration = 5.0
        
        # Create title with symbol and price info
        try:
            last = float(df['close'].iloc[-1])
            prev = float(df['close'].iloc[-2])
            pct = (last / prev - 1.0) * 100
            title_text = f"{symbol} {last:.2f} ({pct:+.2f}%)"
        except Exception:
            title_text = symbol
        
        title = Text(title_text, color=WHITE, font_size=48).to_edge(UP, buff=0.5)
        self.play(FadeIn(title))
        
        # Create axes for the chart
        if len(df) > 0:
            date_range = len(df)
            price_min = float(df[['low']].min().min())
            price_max = float(df[['high']].max().max())
            price_range = price_max - price_min if price_max > price_min else price_max * 0.1
            
            ax = Axes(
                x_range=[0, date_range, max(1, date_range // 10)],
                y_range=[price_min - price_range * 0.1, price_max + price_range * 0.1, price_range / 5],
                x_length=9,
                y_length=14,
                axis_config={"color": WHITE, "stroke_width": 2},
            ).shift(DOWN * 0.5)
            
            self.play(Create(ax))
            
            # Draw candlesticks
            candles = VGroup()
            sample_size = min(50, len(df))  # Limit to 50 candles for performance
            step = max(1, len(df) // sample_size)
            
            for i in range(0, len(df), step):
                row = df.iloc[i]
                x_pos = i
                open_price = float(row['open'])
                close_price = float(row['close'])
                high_price = float(row['high'])
                low_price = float(row['low'])
                
                # Body
                body_height = abs(close_price - open_price)
                body_color = GREEN if close_price >= open_price else RED
                body_y = (open_price + close_price) / 2
                
                body = Rectangle(
                    width=0.15,
                    height=ax.y_axis.unit_size * body_height / ax.y_range[2],
                    fill_color=body_color,
                    fill_opacity=1.0,
                    stroke_color=body_color,
                    stroke_width=1,
                )
                body.move_to(ax.coords_to_point(x_pos, body_y))
                
                # Wicks
                wick_top = ax.coords_to_point(x_pos, high_price)
                wick_bottom = ax.coords_to_point(x_pos, low_price)
                wick = Line(wick_top, wick_bottom, color=body_color, stroke_width=2)
                
                candle = VGroup(body, wick)
                candles.add(candle)
            
            self.play(Create(candles), run_time=min(duration - 2, 3.0))
            self.wait(duration - 3.0)
        else:
            self.wait(duration)


class PercentChangeChartScene(Scene):
    """Manim scene for percentage change chart."""
    
    def construct(self):
        # Get data from module-level store
        if not _current_scene_data:
            self.wait(1)
            return
        df = _current_scene_data.get('df')
        symbol = _current_scene_data.get('symbol')
        days = _current_scene_data.get('days', 5)
        if df is None or symbol is None:
            self.wait(1)
            return
        
        duration = 4.0
        df_filtered = df[df["symbol"] == symbol].sort_values("timestamp").tail(days)
        
        if df_filtered.empty:
            self.wait(duration)
            return
        
        title = Text(f"{symbol} % Change", color=WHITE, font_size=40).to_edge(UP, buff=0.3)
        self.play(FadeIn(title))
        
        pct = (df_filtered["close"].pct_change() * 100).fillna(0)
        
        if len(pct) > 1:
            x_max = len(pct)
            y_min = float(pct.min()) - 1
            y_max = float(pct.max()) + 1
            y_range = y_max - y_min if y_max > y_min else 2.0
            
            ax = Axes(
                x_range=[0, x_max, 1],
                y_range=[y_min, y_max, y_range / 4],
                x_length=9,
                y_length=10,
                axis_config={"color": WHITE, "stroke_width": 2},
            ).shift(DOWN * 0.3)
            
            self.play(Create(ax))
            
            # Draw line
            points = [ax.coords_to_point(i, float(pct.iloc[i])) for i in range(len(pct))]
            line = Line(points[0], points[0], color=ORANGE, stroke_width=4)
            
            for i in range(1, len(points)):
                new_line = Line(points[i-1], points[i], color=ORANGE, stroke_width=4)
                line = VGroup(line, new_line)
            
            self.play(Create(line), run_time=min(duration - 1.5, 2.5))
            self.wait(duration - 2.5)
        else:
            self.wait(duration)


class VolumeChartScene(Scene):
    """Manim scene for volume chart."""
    
    def construct(self):
        # Get data from module-level store
        if not _current_scene_data:
            self.wait(1)
            return
        df = _current_scene_data.get('df')
        symbol = _current_scene_data.get('symbol')
        days = _current_scene_data.get('days', 30)
        if df is None or symbol is None:
            self.wait(1)
            return
        
        duration = 4.0
        df_filtered = df[df["symbol"] == symbol].sort_values("timestamp").tail(days)
        
        if df_filtered.empty:
            self.wait(duration)
            return
        
        title = Text(f"{symbol} Volume", color=WHITE, font_size=40).to_edge(UP, buff=0.3)
        self.play(FadeIn(title))
        
        volumes = df_filtered["volume"]
        if len(volumes) > 1:
            x_max = len(volumes)
            y_max = float(volumes.max()) * 1.1
            
            ax = Axes(
                x_range=[0, x_max, max(1, x_max // 5)],
                y_range=[0, y_max, y_max / 5],
                x_length=9,
                y_length=10,
                axis_config={"color": WHITE, "stroke_width": 2},
            ).shift(DOWN * 0.3)
            
            self.play(Create(ax))
            
            # Draw bars
            bars = VGroup()
            bar_width = 0.6
            sample_size = min(20, len(volumes))
            step = max(1, len(volumes) // sample_size)
            
            for i in range(0, len(volumes), step):
                vol = float(volumes.iloc[i])
                bar = Rectangle(
                    width=bar_width,
                    height=ax.y_axis.unit_size * vol / ax.y_range[2],
                    fill_color=BLUE,
                    fill_opacity=0.7,
                    stroke_color=BLUE,
                )
                bar.move_to(ax.coords_to_point(i, vol / 2))
                bars.add(bar)
            
            self.play(Create(bars), run_time=min(duration - 1.5, 2.5))
            self.wait(duration - 2.5)
        else:
            self.wait(duration)


def render_manim_scene(scene_class, scene_kwargs: dict, output_path: str, output_format: str = "mov"):
    """Render a Manim scene to file with transparent background.
    
    Args:
        scene_class: Manim Scene class to render
        scene_kwargs: Keyword arguments to store for scene access
        output_path: Output file path
        output_format: "mov" or "png"
    """
    if not MANIM_AVAILABLE:
        raise ImportError("Manim is not available. Install with: pip install manim")
    
    # Configure for transparency BEFORE creating scene
    configure_manim_transparent(output_format)
    
    # Store data in module-level variable (scenes access this in construct())
    global _current_scene_data
    _current_scene_data = scene_kwargs.copy()
    
    # Create scene instance and render
    scene = scene_class()
    scene.render()
    
    # Clean up data store
    _current_scene_data = {}
    
    # Find the rendered file and move it to output_path
    # Manim saves to media/videos/<module>/<quality>/<scene_name>.<ext>
    media_root = Path("media/videos")
    scene_name = scene_class.__name__
    
    if output_format == "mov":
        pattern = f"*{scene_name}*.mov"
    else:
        pattern = f"*{scene_name}*.png"
    
    candidates = list(media_root.rglob(pattern))
    if candidates:
        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        # For PNG sequences, need to handle directory
        if output_format == "png" and latest.is_dir():
            import shutil
            if output_path_obj.exists():
                shutil.rmtree(output_path_obj)
            shutil.copytree(latest, output_path_obj)
        else:
            import shutil
            shutil.copy(latest, output_path_obj)
        
        return str(output_path_obj.resolve())
    else:
        raise FileNotFoundError(f"Could not find rendered output for {scene_name}")


def main(args):
    if not MANIM_AVAILABLE:
        print("Error: Manim is required but not installed.", file=sys.stderr)
        print("Install with: pip install manim", file=sys.stderr)
        sys.exit(1)
    
    os.makedirs(args.outdir, exist_ok=True)
    df = pd.read_csv(args.cache, parse_dates=["timestamp"]) if args.cache else None
    
    with open(args.story) as f:
        story = json.load(f)
    
    # Determine output format
    output_format = getattr(args, 'format', 'mov').lower()
    if output_format not in ['mov', 'png']:
        output_format = 'mov'
    
    # Choose symbols
    symbols = ["SPY", "GLD", "SLV"]
    if df is not None:
        extra = [s for s in sorted(df["symbol"].unique()) if s not in symbols]
        if extra:
            symbols.append(extra[0])
    
    chart_map = {"scenes": [], "manim_clips": []}
    scene_idx = 1
    available = list(df["symbol"].unique()) if df is not None else symbols
    
    for sym in [s for s in symbols if s in available][:4]:
        if df is None:
            continue
            
        sym_df = df[df["symbol"] == sym]
        if sym_df.empty:
            continue
        
        # Price chart
        price_out = os.path.join(args.outdir, f"scene_{scene_idx:02d}_{sym}_price.{output_format}")
        try:
            render_manim_scene(
                CandlestickChartScene,
                {"df": sym_df, "symbol": sym},
                price_out,
                output_format
            )
            chart_map["scenes"].append({
                "scene": scene_idx,
                "type": "price",
                "symbol": sym,
                "file": price_out
            })
            chart_map["manim_clips"].append(price_out)
        except Exception as e:
            print(f"Error rendering price chart for {sym}: {e}", file=sys.stderr)
        scene_idx += 1
        
        # Percent change chart
        pct_out = os.path.join(args.outdir, f"scene_{scene_idx:02d}_{sym}_pct.{output_format}")
        try:
            render_manim_scene(
                PercentChangeChartScene,
                {"df": df, "symbol": sym, "days": 5},
                pct_out,
                output_format
            )
            chart_map["scenes"].append({
                "scene": scene_idx,
                "type": "pct",
                "symbol": sym,
                "file": pct_out
            })
            chart_map["manim_clips"].append(pct_out)
        except Exception as e:
            print(f"Error rendering pct chart for {sym}: {e}", file=sys.stderr)
        scene_idx += 1
        
        # Volume chart
        vol_out = os.path.join(args.outdir, f"scene_{scene_idx:02d}_{sym}_vol.{output_format}")
        try:
            render_manim_scene(
                VolumeChartScene,
                {"df": df, "symbol": sym, "days": 30},
                vol_out,
                output_format
            )
            chart_map["scenes"].append({
                "scene": scene_idx,
                "type": "volume",
                "symbol": sym,
                "file": vol_out
            })
            chart_map["manim_clips"].append(vol_out)
        except Exception as e:
            print(f"Error rendering volume chart for {sym}: {e}", file=sys.stderr)
        scene_idx += 1
    
    # Write metadata
    meta_out = os.path.join(args.outdir, "chart_meta.json")
    with open(meta_out, "w") as f:
        json.dump(chart_map, f, indent=2)
    
    print("Wrote Manim charts to", args.outdir)
    print("Meta:", meta_out)
    print(f"Format: {output_format.upper()} with transparent background")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--story", required=True, help="story JSON path")
    p.add_argument("--cache", required=True, help="cache CSV path")
    p.add_argument("--outdir", required=True, help="output directory for charts")
    p.add_argument("--format", default="mov", choices=["mov", "png"], 
                   help="Output format: mov (ProRes 4444) or png (image sequence)")
    args = p.parse_args()
    main(args)
