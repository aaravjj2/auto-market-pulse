#!/usr/bin/env python3
"""Create a mobile thumbnail PNG from a chart and headline text."""
import argparse
import os
from PIL import Image, ImageDraw, ImageFont


def make_thumbnail(chart_path, headline, outpath, size=(640, 1280)):
    img = Image.open(chart_path).convert("RGB")
    img = img.resize(size)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 80)
    except Exception:
        font = ImageFont.load_default()
    # Place headline near top
    x = 40
    y = 40
    # darken background strip
    draw.rectangle([(0, y - 20), (size[0], y + 180)], fill=(0, 0, 0, 180))
    draw.text((x, y), headline, font=font, fill=(255, 255, 255))
    img.save(outpath, quality=90)


def main(args):
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    make_thumbnail(args.chart, args.headline, args.output)
    print("Wrote thumbnail:", args.output)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--chart", required=True)
    p.add_argument("--headline", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    main(args)
