"""Freeze a reconstruction into a versioned artifact directory.

``freeze_artifacts`` is the Python equivalent of::

    mkdir -p artifacts/v1
    cp dense/fused.ply artifacts/v1/
    colmap model_converter --input_path sparse/0 \\
        --output_path artifacts/v1/poses --output_type TXT

The dense point cloud is copied to ``fused.ply`` whatever filename the dense
backend used. The COLMAP model is written as text into ``poses/`` (``cameras.txt``,
``images.txt``, ``points3D.txt``, plus ``rigs.txt``/``frames.txt`` for newer
models).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import pycolmap

logger = logging.getLogger(__name__)

POINT_CLOUD_FILENAME = "fused.ply"
POSES_DIRNAME = "poses"
REQUIRED_POSE_FILES = ("cameras.txt", "images.txt", "points3D.txt")


def freeze_artifacts(
    sparse_model_path: str | Path,
    point_cloud_path: str | Path,
    artifact_dir: str | Path,
) -> Path:
    """Write a stable artifact directory for downstream consumers.

    ``sparse_model_path`` is a numbered COLMAP model directory such as
    ``sparse/0``. ``point_cloud_path`` is the dense point cloud produced by
    ``run_dense_reconstruction`` (``fused.ply`` or ``scene_dense.ply``). Both are
    copied/exported beneath ``artifact_dir`` and that directory is returned.

    Raises ``FileNotFoundError`` when an input is missing and ``RuntimeError``
    when the model cannot be written as text.
    """
    model = Path(sparse_model_path)
    cloud = Path(point_cloud_path)
    artifact = Path(artifact_dir)

    if not model.is_dir():
        raise FileNotFoundError(f"COLMAP model directory not found: {model}")
    if not cloud.is_file():
        raise FileNotFoundError(f"dense point cloud not found: {cloud}")

    poses_dir = artifact / POSES_DIRNAME
    poses_dir.mkdir(parents=True, exist_ok=True)

    try:
        reconstruction = pycolmap.Reconstruction(str(model))
        reconstruction.write_text(str(poses_dir))
    except Exception as exc:  # noqa: BLE001 - surface COLMAP's reason
        raise RuntimeError(
            f"could not export COLMAP model {model} as text to {poses_dir}: {exc}"
        ) from exc

    missing = [
        name for name in REQUIRED_POSE_FILES if not (poses_dir / name).is_file()
    ]
    if missing:
        raise RuntimeError(
            f"COLMAP text export missing {', '.join(missing)} in {poses_dir}"
        )

    frozen_cloud = artifact / POINT_CLOUD_FILENAME
    try:
        shutil.copy2(cloud, frozen_cloud)
    except OSError as exc:
        raise RuntimeError(f"could not copy {cloud} to {frozen_cloud}: {exc}") from exc

    logger.info("froze %s and %s into %s", model, cloud, artifact)
    return artifact
