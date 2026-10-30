"""COLMAP feature extraction for the frames the Process job produced.

``extract_features`` is importable and has no import-time side effects. It reads
the JPEGs written by ``extract_frames`` and writes a COLMAP database containing
the detected SIFT features. ``run.pipeline`` runs it once per session,
after frame extraction and before feature matching.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pycolmap

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def extract_features(
    images_dir: str | Path, database_path: str | Path
) -> Path:
    """Extract SIFT features from every image in ``images_dir``.

    Writes the COLMAP database to ``database_path`` (created when missing) and
    returns it. Raises ``FileNotFoundError`` when the image directory is missing
    and ``ValueError`` when it holds no supported images.
    """
    images = Path(images_dir)
    database = Path(database_path)

    if not images.is_dir():
        raise FileNotFoundError(f"image folder not found: {images}")

    image_names = sorted(
        file.name
        for file in images.iterdir()
        if file.is_file() and file.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not image_names:
        raise ValueError(f"no images found in {images}")

    database.parent.mkdir(parents=True, exist_ok=True)

    logger.info("extracting SIFT features from %d images in %s", len(image_names), images)
    pycolmap.extract_features(
        database_path=str(database),
        image_path=str(images),
        image_names=image_names,
        camera_mode=pycolmap.CameraMode.SINGLE,
    )
    logger.info("feature extraction wrote %s", database)
    return database
