"""Photo normalization for the Process job's hand-off images.

The job writes one normalized JPEG per usable photo into ``processed/images`` so
downstream stages never have to deal with HEIC, orientation metadata, or huge
originals. Unreadable files are skipped rather than failing the whole job.
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

# Sampling knobs for turning a photo into a normalized still. Bounded so a huge
# upload cannot tie up the worker for minutes.
MAX_IMAGE_DIM = 2000
JPEG_QUALITY = 90


def _fit(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= MAX_IMAGE_DIM:
        return image
    scale = MAX_IMAGE_DIM / longest
    return cv2.resize(
        image,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )


def _imread_pillow(source: Path) -> np.ndarray | None:
    """Fallback for formats OpenCV cannot decode (HEIC from iPhones, for example)."""
    try:
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            rgb = np.asarray(image.convert("RGB"))
    except Exception as exc:  # noqa: BLE001 - a bad photo must not fail the job
        logger.warning("could not read image %s: %s", source, exc)
        return None
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def process_photo(source: Path, images_dir: Path, stem: str) -> dict | None:
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        image = _imread_pillow(source)
    if image is None:
        return None
    dest = images_dir / f"{stem}.jpg"
    if not cv2.imwrite(str(dest), _fit(image), [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]):
        return None
    return {"image": dest.name, "frame_index": None}


def prepare_asset(source: dict, path: Path, images_dir: Path, indexed: bool) -> list[dict]:
    """Runs in a worker thread. Returns one record per produced image.

    Videos are not normalized here: they are handed to ``run.pipeline()`` and
    handled by ``extract_frames``, so this returns nothing for them.
    """
    if source["kind"] == "video":
        return []

    stem = source["asset_id"] if indexed else Path(source["stored_path"]).stem
    photo = process_photo(path, images_dir, stem)
    if not photo:
        return []
    return [
        {
            **photo,
            "source_asset_id": source["asset_id"],
            "source_kind": source["kind"],
            "source_filename": source["original_filename"],
        }
    ]
