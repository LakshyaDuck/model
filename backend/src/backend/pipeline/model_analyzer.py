"""Model statistics for a COLMAP sparse reconstruction.

``analyze_model`` is importable and has no import-time side effects. It is the
Python equivalent of::

    colmap model_analyzer --path sparse/0

It loads one model directory, logs the same summary the COLMAP CLI prints, and
returns the statistics as a dict for later pipeline stages.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pycolmap

logger = logging.getLogger(__name__)


def analyze_model(model_path: str | Path) -> dict:
    """Load a COLMAP model directory and return its statistics.

    Raises ``FileNotFoundError`` when the directory is missing and
    ``RuntimeError`` when COLMAP cannot read a model from it.
    """
    path = Path(model_path)
    if not path.is_dir():
        raise FileNotFoundError(f"COLMAP model directory not found: {path}")

    try:
        reconstruction = pycolmap.Reconstruction(str(path))
    except Exception as exc:  # noqa: BLE001 - surface COLMAP's reason
        raise RuntimeError(f"could not read COLMAP model at {path}: {exc}") from exc

    stats = {
        "path": str(path),
        "num_rigs": reconstruction.num_rigs(),
        "num_cameras": reconstruction.num_cameras(),
        "num_frames": reconstruction.num_frames(),
        "num_reg_frames": reconstruction.num_reg_frames(),
        "num_images": reconstruction.num_images(),
        "num_reg_images": reconstruction.num_reg_images(),
        "num_points3D": reconstruction.num_points3D(),
        "num_observations": reconstruction.compute_num_observations(),
        "mean_track_length": reconstruction.compute_mean_track_length(),
        "mean_observations_per_image": (
            reconstruction.compute_mean_observations_per_reg_image()
        ),
        "mean_reprojection_error": reconstruction.compute_mean_reprojection_error(),
    }

    logger.info("model analysis for %s:\n%s", path, reconstruction.summary())
    return stats
