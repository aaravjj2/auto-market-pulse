#!/usr/bin/env python3
"""Generate three contextual Manim animations for the dollar video.

Usage: run this script directly. It requires `manim` installed in the Python environment.
It will render three scenes and write the resulting mp4 files under the story output directory.

Scene outputs:
- manim_scene_A.mp4  (0:00-0:20) Housing Gap
- manim_scene_B.mp4  (0:20-0:45) Money Spike
- manim_scene_C.mp4  (0:45-end) Purchasing Power Plunge

Notes:
- The script configures Manim to render vertical 1080x1920 MP4s with pure black background.
- Timing: each scene uses `run_time` to roughly match target durations; you can adjust them if needed.
"""
from __future__ import annotations

import os
from pathlib import Path
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
    GrowFromEdge,
    DOWN,
    UP,
    RIGHT,
    LEFT,
    DOWN,
    BLACK,
    WHITE,
)


# Output directory (matches other pipeline outputs)
OUT_DIR = Path("output/smoke_test/dollar")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def configure_manim():
    # 9:16 vertical 1080x1920, pure black background
    config.pixel_width = 1080
    config.pixel_height = 1920
    config.frame_rate = 30
    config.background_color = BLACK


class HousingGap(Scene):
    """Segment A (0:00-0:20) - Dual bar chart: $23k vs $400k"""

    def construct(self):
        duration = 20
        title = Text("The Housing Gap", color=WHITE).to_edge(UP)
        self.play(FadeIn(title))

        # Create axes baseline
        baseline = Line(LEFT * 4, RIGHT * 4, color=WHITE).shift(DOWN * 1.5)
        self.play(Create(baseline))

        # Bars (empty at start)
        left_bar = Rectangle(width=1.2, height=0.01, fill_color=WHITE, fill_opacity=1).move_to(LEFT * 1.5 + DOWN * 0.5)
        right_bar = Rectangle(width=1.2, height=0.01, fill_color="#ff0055", fill_opacity=1).move_to(RIGHT * 1.5 + DOWN * 0.5)
        left_label = Text("$23k", color=BLACK).scale(0.6)
        right_label = Text("$400k", color=BLACK).scale(0.6)

        # Place labels initially hidden above expected top
        left_label.next_to(left_bar, UP)
        right_label.next_to(right_bar, UP)

        self.add(left_bar, right_bar)

        # Animate bars growing from baseline to target heights
        target_left = 2.2
        target_right = 8.5
        self.play(left_bar.animate.scale_to_fit_height(target_left), right_bar.animate.scale_to_fit_height(target_right), run_time=2.2)

        # Move labels to top of bars
        left_label.next_to(left_bar, UP)
        right_label.next_to(right_bar, UP)
        self.play(FadeIn(left_label), FadeIn(right_label))

        subtitle = Text("Housing costs have exploded", color=WHITE).scale(0.6).to_edge(DOWN)
        self.play(FadeIn(subtitle))
        self.wait(duration - 3)


class MoneySpike(Scene):
    """Segment B (0:20-0:45) - Neon green line chart drawing left-to-right with spike"""

    def construct(self):
        duration = 25
        title = Text("M2 Money Supply", color=WHITE).to_edge(UP)
        self.play(FadeIn(title))

        # Axes setup
        ax = Axes(x_range=[0, 10, 1], y_range=[0, 12, 2], x_length=8, y_length=12)
        ax.move_to(DOWN * 0.2)
        self.play(Create(ax))

        # Construct coordinates with a strong spike near the right
        xs = list(range(11))
        ys = [0.5, 0.6, 0.8, 1.2, 1.6, 2.2, 3.0, 4.0, 5.5, 11.5, 11.8]
        coords = [ax.coords_to_point(x, y) for x, y in zip(xs, ys)]

        # Draw the line segment by segment; spike is the penultimate segment
        segments = [Line(coords[i], coords[i+1], color="#00ff88", stroke_width=8) for i in range(len(coords)-1)]

        # We'll time the drawing so the spike (index len-2) happens at ~80% of scene
        # Try to load audio word timestamps to sync the spike more precisely.
        timestamps_path = OUT_DIR / "audio_dollar_word_timestamps.json"
        spike_target_word = "vertical"
        scene_start = 20.0
        spike_time_abs = None
        if timestamps_path.exists():
            try:
                with open(timestamps_path, "r") as fh:
                    ts = json.load(fh)
                    for w in ts.get("words", []):
                        if w["word"].lower().strip(".,") == spike_target_word:
                            spike_time_abs = float(w["start"])
                            break
            except Exception:
                spike_time_abs = None

        total_segments = len(segments)
        spike_index = total_segments - 2

        if spike_time_abs is not None:
            # compute relative spike time inside this scene
            rel_spike = max(0.0, spike_time_abs - scene_start)
            # distribute time before the spike across the earlier segments
            num_pre = max(1, spike_index)
            pre_total_time = min(duration * 0.95, rel_spike)
            base_rt = pre_total_time / num_pre
            for i, seg in enumerate(segments):
                if i < spike_index:
                    self.play(Create(seg), run_time=base_rt)
                elif i == spike_index:
                    # ensure spike coincides roughly with rel_spike
                    self.play(Create(seg), run_time=0.5)
                    self.play(Create(Line(segments[i].get_start(), segments[i].get_end(), color="#00ff88", stroke_width=14)), run_time=0.4)
                else:
                    self.play(Create(seg), run_time=0.2)
        else:
            base_rt = (duration * 0.9) / total_segments
            for i, seg in enumerate(segments):
                # emphasize spike
                if i == total_segments - 2:
                    self.play(Create(seg), run_time=base_rt * 1.2)
                    # draw a thicker overlay for dramatic effect
                    self.play(Create(Line(segments[i].get_start(), segments[i].get_end(), color="#00ff88", stroke_width=14)), run_time=0.4)
                else:
                    self.play(Create(seg), run_time=base_rt)

        note = Text("2020: Vertical spike", color=WHITE).scale(0.6).to_edge(DOWN)
        self.play(FadeIn(note))
        self.wait(duration - 3)


class PurchasingPower(Scene):
    """Segment C (0:45-End) - Purchasing power plunges downwards"""

    def construct(self):
        duration = 20
        title = Text("Purchasing Power", color=WHITE).to_edge(UP)
        self.play(FadeIn(title))

        ax = Axes(x_range=[0, 10, 1], y_range=[0, 10, 2], x_length=8, y_length=10)
        ax.move_to(DOWN * 0.2)
        self.play(Create(ax))

        # line starts high and gradually trends down, then crashes
        pts = [ (0, 8), (2,7.5), (4,7.0), (6,5.5), (8,3.0), (9,2.0), (10,1.0) ]
        coords = [ax.coords_to_point(x, y) for x, y in pts]
        segments = [Line(coords[i], coords[i+1], color="#ff0044", stroke_width=8) for i in range(len(coords)-1)]

        # Draw initial gentle decline and time final crash to audio if available
        timestamps_path = OUT_DIR / "audio_dollar_word_timestamps.json"
        crash_target_word = "half"
        scene_start = 45.0
        crash_time_abs = None
        if timestamps_path.exists():
            try:
                with open(timestamps_path, "r") as fh:
                    ts = json.load(fh)
                    for w in ts.get("words", []):
                        # match "half" which often appears with punctuation
                        if w["word"].lower().strip(".,") == crash_target_word:
                            crash_time_abs = float(w["start"])
                            break
            except Exception:
                crash_time_abs = None

        if crash_time_abs is not None:
            rel_crash = max(0.0, crash_time_abs - scene_start)
            # time before crash should be at most duration*0.95
            pre_total = min(duration * 0.95, rel_crash)
            num_pre = max(1, len(segments) - 1)
            per_seg = pre_total / num_pre
            for seg in segments[:-1]:
                self.play(Create(seg), run_time=per_seg)
            # final crash timed to occur around rel_crash
            self.play(Create(segments[-1]), run_time=1.0)
        else:
            # fallback behaviour
            for i, seg in enumerate(segments[:-1]):
                self.play(Create(seg), run_time=1.2)
            self.play(Create(segments[-1]), run_time=1.0)

        label = Text("Purchasing Power", color=WHITE).scale(0.7).next_to(segments[0], UP)
        self.play(FadeIn(label))

        self.wait(duration - (1.2 * (len(segments)-1) + 1.0 + 2))


def render_all():
    configure_manim()
    # Render each scene and move output files into OUT_DIR with friendlier names
    scenes = [
        (HousingGap, "manim_scene_A.mp4"),
        (MoneySpike, "manim_scene_B.mp4"),
        (PurchasingPower, "manim_scene_C.mp4"),
    ]

    for SceneClass, fname in scenes:
        print("Rendering", SceneClass.__name__)
        scene = SceneClass()
        scene.render()
        # manim writes files to media/videos/<module>/<scene>... find latest file
        # We'll attempt to move the most recent mp4 for this scene into OUT_DIR
        # Search media/videos for a file that contains SceneClass.__name__
        media_root = Path("media/videos")
        candidates = list(media_root.rglob(f"*{SceneClass.__name__}*.mp4"))
        if candidates:
            latest = max(candidates, key=lambda p: p.stat().st_mtime)
            dest = OUT_DIR / fname
            print("Moving", latest, "->", dest)
            try:
                dest.unlink(missing_ok=True)
            except Exception:
                pass
            latest.replace(dest)
        else:
            print("Warning: could not find rendered file for", SceneClass.__name__)


if __name__ == "__main__":
    render_all()
