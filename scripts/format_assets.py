#!/usr/bin/env python3
"""Create square and landscape WebP variants for raw images."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
VARIANTS = {
    "1x1": (1080, 1080),
    "16x9": (1200, 675),
}


def cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    width, height = size
    scale = max(width / image.width, height / image.height)
    resized = image.resize(
        (round(image.width * scale), round(image.height * scale)),
        Image.Resampling.LANCZOS,
    )
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def process_image(source: Path, raw_dir: Path, output_dir: Path) -> list[Path]:
    relative = source.relative_to(raw_dir)
    destination_dir = output_dir / relative.parent
    destination_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened)
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA" if "transparency" in image.info else "RGB")
        for variant, size in VARIANTS.items():
            destination = destination_dir / f"{source.stem}-{variant}.webp"
            cover(image, size).save(destination, "WEBP", quality=84, method=6)
            outputs.append(destination)
    return outputs


def process_all(raw_dir: Path, output_dir: Path) -> list[Path]:
    if not raw_dir.is_dir():
        raise RuntimeError(f"Raw media directory does not exist: {raw_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = sorted(
        path for path in raw_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
    outputs = []
    for source in sources:
        outputs.extend(process_image(source, raw_dir, output_dir))
    print(f"Processed {len(sources)} images into {len(outputs)} WebP assets")
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "media" / "raw")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "media" / "processed")
    args = parser.parse_args()
    process_all(args.raw_dir, args.output_dir)


if __name__ == "__main__":
    main()
