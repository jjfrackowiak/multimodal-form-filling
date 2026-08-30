from __future__ import annotations

import hashlib
import io
from collections import defaultdict
from pathlib import Path

from PIL import Image

# Production inputs. HEIC is not accepted — convert before upload if a phone
# still emits it. Cloud Run does not convert.
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
UNSUPPORTED_EXT = {".heic", ".heif"}
MAX_EDGE = 1536
JPEG_QUALITY = 80


def suffix(name: str) -> str:
    return Path(name).suffix.lower()


def is_supported_image(name: str) -> bool:
    return suffix(name) in IMAGE_EXT


def check_image_name(name: str) -> None:
    ext = suffix(name)
    if ext in UNSUPPORTED_EXT:
        raise ValueError(f"unsupported image type {ext} (jpeg/png/webp only; not heic)")
    if ext not in IMAGE_EXT:
        raise ValueError(f"not an image: {name}")


def list_images(folder: Path) -> list[Path]:
    return sorted(
        (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXT),
        key=lambda p: p.name,
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def collapse_duplicates(paths: list[Path]) -> tuple[list[Path], list[list[str]]]:
    by_hash: dict[str, list[Path]] = defaultdict(list)
    for p in paths:
        by_hash[sha256_file(p)].append(p)
    unique: list[Path] = []
    pairs: list[list[str]] = []
    for group in by_hash.values():
        group = sorted(group, key=lambda p: p.name)
        unique.append(group[0])
        for extra in group[1:]:
            pairs.append([group[0].name, extra.name])
    unique.sort(key=lambda p: p.name)
    return unique, pairs


def jpeg_bytes(path: Path, max_edge: int = MAX_EDGE) -> bytes:
    """Downscale so Vertex calls stay small enough for a tool in a tight loop."""
    with Image.open(path) as im:
        rgb = im.convert("RGB")
        rgb.thumbnail((max_edge, max_edge))
        buf = io.BytesIO()
        rgb.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return buf.getvalue()
