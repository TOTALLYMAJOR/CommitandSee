"""Generate the deterministic CommitandSee Windows icon assets."""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


CANVAS = 1024
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def cubic(start, control_1, control_2, end, steps=48):
    points = []
    for index in range(steps + 1):
        t = index / steps
        inverse = 1 - t
        points.append((
            round(inverse**3 * start[0] + 3 * inverse**2 * t * control_1[0]
                  + 3 * inverse * t**2 * control_2[0] + t**3 * end[0]),
            round(inverse**3 * start[1] + 3 * inverse**2 * t * control_1[1]
                  + 3 * inverse * t**2 * control_2[1] + t**3 * end[1]),
        ))
    return points


def stroke(draw, points, color, width):
    draw.line(points, fill=color, width=width, joint="curve")
    radius = width // 2
    for x, y in (points[0], points[-1]):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)


def render():
    image = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((36, 36, 988, 988), radius=224, fill="#10291f",
                           outline="#2d5c49", width=20)

    c_points = (
        cubic((744, 270), (625, 105), (290, 115), (202, 470))
        + cubic((202, 470), (112, 805), (535, 930), (752, 744))[1:]
    )
    stroke(draw, c_points, "#7be1ad", 126)

    s_points = (
        cubic((820, 278), (690, 145), (475, 180), (454, 348))
        + cubic((454, 348), (438, 478), (690, 485), (714, 548))[1:]
        + cubic((714, 548), (770, 630), (774, 724), (690, 775))[1:]
        + cubic((690, 775), (585, 846), (405, 820), (354, 728))[1:]
    )
    stroke(draw, s_points, "#10291f", 164)
    stroke(draw, s_points, "#f2cf73", 108)
    return image


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--png", type=Path,
                        default=root / "docs" / "images" / "commitandsee-icon.png")
    parser.add_argument("--ico", type=Path,
                        default=root / "packaging" / "CommitandSee.ico")
    args = parser.parse_args()

    image = render()
    args.png.parent.mkdir(parents=True, exist_ok=True)
    args.ico.parent.mkdir(parents=True, exist_ok=True)
    image.resize((512, 512), Image.Resampling.LANCZOS).save(args.png, optimize=True)
    image.save(args.ico, format="ICO", sizes=[(size, size) for size in ICO_SIZES])


if __name__ == "__main__":
    main()
