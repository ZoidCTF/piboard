"""Crop photos to 16:9 at 1920x1080 and mute them for use behind dashboard text.

usage: prep_photos.py SRC_DIR OUT_DIR   (needs Pillow; run it on a PC, not the Pi)
Focus is (x, y) in 0..1: where the crop window centres within the image.
Files not listed in FOCUS are cropped around the centre.
"""
import sys
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps

Image.MAX_IMAGE_PIXELS = 60_000_000  # the Knox panorama is ~29 MP

W, H = 1920, 1080
SATURATION = 0.78
BRIGHTNESS = 0.85

FOCUS = {
    "knox-panorama.jpg": (0.42, 0.5),
    "okanagan-valley.jpg": (0.5, 0.45),
    "osoyoos-vineyards.jpg": (0.5, 0.5),
    "knox-view.jpg": (0.5, 0.55),
    "naramata-bench.jpg": (0.5, 0.5),
    "dilworth-view.jpg": (0.52, 0.5),
}


def prep(src, dst, focus):
    img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    img = ImageOps.fit(img, (W, H), Image.LANCZOS, centering=focus)
    img = ImageEnhance.Color(img).enhance(SATURATION)
    img = ImageEnhance.Brightness(img).enhance(BRIGHTNESS)
    img.save(dst, "JPEG", quality=86, optimize=True, progressive=True)


def main():
    src_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    for src in sorted(src_dir.iterdir()):
        if src.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            continue
        dst = out_dir / (src.stem + ".jpg")
        prep(src, dst, FOCUS.get(src.name, (0.5, 0.5)))
        print(f"{dst.name}: {dst.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
