"""
One-off script that draws PDFImageMerger's app icon and exports it as PNG
(Linux/AppImage) and ICO (Windows). No external design tool needed — plain
Pillow shapes. Re-run after editing to regenerate assets/icon.png/.ico.
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).resolve().parent

# Franken UI "zinc" theme colors (see frontend/vendor/franken-ui/core.min.css)
BG = (9, 9, 11, 255)  # near-black, matches the app's dark background
PAGE_BACK = (82, 82, 91, 255)  # zinc-600ish
PAGE_FRONT = (250, 250, 250, 255)  # near-white
ACCENT = (244, 63, 94, 255)  # rose accent, stands for "images -> "


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pad = round(size * 0.12)
    radius = round(size * 0.10)

    # Background rounded square.
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=round(size * 0.18), fill=BG)

    # Back page (slightly offset, representing "multiple images").
    back = [pad + size * 0.14, pad, size - pad, size - pad - size * 0.14]
    d.rounded_rectangle(back, radius=radius, fill=PAGE_BACK)

    # Front page (the merged PDF).
    front = [pad, pad + size * 0.14, size - pad - size * 0.14, size - pad]
    d.rounded_rectangle(front, radius=radius, fill=PAGE_FRONT)

    # Small accent dot + bar on the front page, suggesting an embedded image.
    fx0, fy0, fx1, fy1 = front
    fw, fh = fx1 - fx0, fy1 - fy0
    img_rect = [fx0 + fw * 0.16, fy0 + fh * 0.20, fx0 + fw * 0.62, fy0 + fh * 0.55]
    d.rounded_rectangle(img_rect, radius=round(size * 0.03), fill=ACCENT)
    # A little "mountain" glyph inside the accent rectangle, like a photo icon.
    ix0, iy0, ix1, iy1 = img_rect
    iw, ih = ix1 - ix0, iy1 - iy0
    d.polygon(
        [
            (ix0 + iw * 0.15, iy1 - ih * 0.2),
            (ix0 + iw * 0.40, iy1 - ih * 0.55),
            (ix0 + iw * 0.58, iy1 - ih * 0.35),
            (ix0 + iw * 0.75, iy1 - ih * 0.65),
            (ix0 + iw * 0.90, iy1 - ih * 0.2),
        ],
        fill=PAGE_FRONT,
    )
    # Text lines below, suggesting document/pages.
    for i in range(3):
        y = fy0 + fh * 0.68 + i * fh * 0.11
        d.rounded_rectangle(
            [fx0 + fw * 0.16, y, fx0 + fw * (0.84 if i < 2 else 0.55), y + fh * 0.045],
            radius=round(size * 0.01),
            fill=PAGE_BACK,
        )

    return img


def main() -> None:
    base = draw_icon(1024)
    base.save(OUT_DIR / "icon.png")

    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    base.save(
        OUT_DIR / "icon.ico",
        sizes=[(s, s) for s in ico_sizes],
    )
    print(f"Wrote {OUT_DIR / 'icon.png'} and {OUT_DIR / 'icon.ico'}")


if __name__ == "__main__":
    main()
