"""File inspection only: no transcoding, no normalization.

Whatever the phone sends (HEVC .mov, .webm, HEIC) is stored byte for byte and the
mime is recorded as received.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

THUMB_MAX_PX = 480
FFMPEG_TIMEOUT_SECONDS = 90
_SUFFIX_RE = re.compile(r"^\.[A-Za-z0-9]{1,10}$")


def sha256_file(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def safe_suffix(filename: str | None, mime: str | None) -> str:
    """Extension for the stored file. Never derived from raw path characters."""
    if filename:
        candidate = Path(filename).suffix
        if _SUFFIX_RE.match(candidate):
            return candidate.lower()
    if mime:
        guessed = mimetypes.guess_extension(mime.split(";")[0].strip())
        if guessed:
            return ".heic" if guessed == ".heif" else guessed
    return ".bin"


def make_thumbnail(source: Path, dest: Path, mime: str | None, kind: str) -> Path | None:
    """Best effort: a missing thumbnail must not fail an otherwise good asset."""
    try:
        if kind == "video":
            return _ffmpeg_thumbnail(source, dest)
        if (mime or "").startswith("image/"):
            return _pillow_thumbnail(source, dest)
    except Exception as exc:  # noqa: BLE001 - never let thumbnailing fail the asset
        logger.warning("thumbnail failed for %s (%s): %s", source, kind, exc)
        return None
    return None


def _ffmpeg_thumbnail(source: Path, dest: Path) -> Path | None:
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
            "-i", str(source),
            "-frames:v", "1",
            "-vf", f"scale={THUMB_MAX_PX}:-2:force_original_aspect_ratio=decrease",
            "-q:v", "4",
            str(dest),
        ],
        check=True,
        timeout=FFMPEG_TIMEOUT_SECONDS,
    )
    return dest if dest.exists() else None


def _pillow_thumbnail(source: Path, dest: Path) -> Path | None:
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image.thumbnail((THUMB_MAX_PX, THUMB_MAX_PX))
        image.save(dest, format="JPEG", quality=82)
    return dest