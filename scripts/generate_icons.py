"""One-off icon generator for the PWA manifest — not a runtime dependency.
Draws a simple checkered-flag mark on a racing-red field. Run with:
    python scripts/generate_icons.py
Requires Pillow (`pip install pillow`), which is NOT in requirements.txt
since the app itself never needs it at runtime.
"""

from pathlib import Path

from PIL import Image, ImageDraw

RED = (225, 6, 0, 255)
WHITE = (255, 255, 255, 255)
BLACK = (20, 20, 20, 255)

OUT_DIR = Path(__file__).resolve().parent.parent / "app" / "static" / "icons"


def draw_checkered_flag(size: int, margin_ratio: float) -> Image.Image:
    img = Image.new("RGBA", (size, size), RED)
    draw = ImageDraw.Draw(img)

    margin = int(size * margin_ratio)
    flag_size = size - 2 * margin
    cols = rows = 6
    cell = flag_size / cols

    for row in range(rows):
        for col in range(cols):
            if (row + col) % 2 == 0:
                x0 = margin + col * cell
                y0 = margin + row * cell
                draw.rectangle([x0, y0, x0 + cell, y0 + cell], fill=WHITE)
            else:
                x0 = margin + col * cell
                y0 = margin + row * cell
                draw.rectangle([x0, y0, x0 + cell, y0 + cell], fill=BLACK)

    return img


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Standard icons: flag fills most of the canvas.
    draw_checkered_flag(192, margin_ratio=0.15).save(OUT_DIR / "icon-192.png")
    draw_checkered_flag(512, margin_ratio=0.15).save(OUT_DIR / "icon-512.png")

    # Maskable icon: extra margin so OS masking (circle, squircle, etc.)
    # doesn't clip the flag pattern.
    draw_checkered_flag(512, margin_ratio=0.28).save(OUT_DIR / "icon-512-maskable.png")

    # iOS apple-touch-icon: no transparency, flatten onto the red field.
    apple = draw_checkered_flag(180, margin_ratio=0.15).convert("RGB")
    apple.save(OUT_DIR / "apple-touch-icon.png")

    print(f"Wrote icons to {OUT_DIR}")


if __name__ == "__main__":
    main()
