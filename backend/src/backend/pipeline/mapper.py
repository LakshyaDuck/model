"""COLMAP incremental mapping for a matched database.

``run_mapper`` is importable and has no import-time side effects. It is the
Python equivalent of::

    colmap mapper --database_path database.db --image_path frames --output_path sparse

The reconstructions are written beneath ``output_path`` as numbered model
directories (``0/``, ``1/``, ...), exactly like the COLMAP CLI.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pycolmap

logger = logging.getLogger(__name__)


def run_mapper(
    database_path: str | Path,
    images_dir: str | Path,
    output_path: str | Path,
) -> Path:
    """Run incremental SfM mapping over a matched COLMAP database.

    Returns ``output_path``. Raises ``FileNotFoundError`` when the database or
    image directory is missing. An empty result is logged as a warning rather
    than raised: COLMAP can legitimately find no model in weak captures.
    """
    database = Path(database_path)
    images = Path(images_dir)
    output = Path(output_path)

    if not database.is_file():
        raise FileNotFoundError(
            f"COLMAP database not found: {database}; run extraction and matching first"
        )
    if not images.is_dir():
        raise FileNotFoundError(f"image folder not found: {images}")

    output.mkdir(parents=True, exist_ok=True)

    logger.info("mapping %s with images from %s into %s", database, images, output)
    reconstructions = pycolmap.incremental_mapping(
        database_path=str(database),
        image_path=str(images),
        output_path=str(output),
    )

    if reconstructions:
        logger.info(
            "COLMAP mapping wrote %d reconstruction(s) into %s",
            len(reconstructions),
            output,
        )
    else:
        logger.warning("COLMAP mapping produced no reconstruction in %s", output)
    return output
