"""Gera os ícones do ProdSuite (tomate acolhedor, sem visual "cyber").

Uso:  python3 scripts/generate_icons.py
Requer Pillow (dependência de desenvolvimento).
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "static" / "icons"
ICONS.mkdir(parents=True, exist_ok=True)

MASTER = 1024
LAVENDER = (124, 103, 159)
LAVENDER_LIGHT = (158, 138, 184)
LEAF = (112, 130, 100)
LEAF_DARK = (83, 100, 76)
TOMATO = (217, 123, 110)
TOMATO_LIGHT = (233, 158, 146)


def _background(size: int = MASTER) -> Image.Image:
    """Fundo lavanda pastel com um halo de cor, sem grid nem neon."""
    base = Image.new("RGBA", (size, size), LAVENDER + (255,))
    halo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(halo)
    draw.ellipse(
        [size * 0.12, size * 0.08, size * 0.88, size * 0.92],
        fill=LAVENDER_LIGHT + (90,),
    )
    base.alpha_composite(halo.filter(ImageFilter.GaussianBlur(90)))

    # Fundo sangrando até a borda: o iOS/Android aplicam a máscara desejada.
    return base


def _leaf(draw: ImageDraw.ImageDraw, center: tuple[float, float], angle: float, length: float) -> None:
    cx, cy = center
    radians = math.radians(angle)
    dx, dy = math.cos(radians), math.sin(radians)
    px, py = -dy, dx
    width = length * 0.34
    tip = (cx + dx * length, cy + dy * length)
    left = (cx + px * width, cy + py * width)
    right = (cx - px * width, cy - py * width)
    draw.polygon([left, tip, right], fill=LEAF + (255,))
    draw.ellipse(
        [tip[0] - 9, tip[1] - 9, tip[0] + 9, tip[1] + 9],
        fill=LEAF + (255,),
    )


def _tomato(scale: float = 1.0) -> Image.Image:
    base = _background()
    draw = ImageDraw.Draw(base, "RGBA")
    cx, cy = MASTER / 2, MASTER * 0.56
    body_w = 500 * scale
    body_h = 455 * scale

    shadow = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse(
        [
            cx - body_w * 0.52,
            cy + body_h * 0.18,
            cx + body_w * 0.52,
            cy + body_h * 0.72,
        ],
        fill=(60, 40, 55, 80),
    )
    base.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(28)))

    draw.ellipse(
        [cx - body_w / 2, cy - body_h / 2, cx + body_w / 2, cy + body_h / 2],
        fill=TOMATO + (255,),
    )
    draw.ellipse(
        [
            cx - body_w * 0.32,
            cy - body_h * 0.33,
            cx - body_w * 0.03,
            cy - body_h * 0.08,
        ],
        fill=TOMATO_LIGHT + (120,),
    )
    draw.arc(
        [
            cx - body_w * 0.42,
            cy - body_h * 0.36,
            cx + body_w * 0.42,
            cy + body_h * 0.4,
        ],
        start=160,
        end=340,
        fill=(190, 65, 57, 90),
        width=18,
    )

    draw.rounded_rectangle(
        [cx - 16, cy - body_h * 0.65, cx + 16, cy - body_h * 0.43],
        radius=14,
        fill=LEAF_DARK + (255,),
    )
    leaf_center = (cx, cy - body_h * 0.35)
    for angle in (-160, -120, -80, -40, 0, 40):
        _leaf(draw, leaf_center, angle, body_w * 0.26)

    return base


def main() -> None:
    master = _tomato()
    sizes = {
        "icon-512.png": 512,
        "icon-192.png": 192,
        "apple-touch-icon-180.png": 180,
        "icon-32.png": 32,
        "icon-16.png": 16,
    }
    for name, size in sizes.items():
        image = master.resize((size, size), Image.Resampling.LANCZOS).convert("RGB")
        image.save(ICONS / name, format="PNG", optimize=True)
        print(f"gerado {name} ({size}x{size})")

    maskable = _tomato(scale=0.82).resize((512, 512), Image.Resampling.LANCZOS).convert("RGB")
    maskable.save(ICONS / "icon-maskable-512.png", format="PNG", optimize=True)
    print("gerado icon-maskable-512.png")

    master.convert("RGB").save(
        ICONS / "favicon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
    )
    print("gerado favicon.ico")


if __name__ == "__main__":
    main()
