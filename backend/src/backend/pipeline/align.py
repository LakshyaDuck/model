"""Align a cleaned point cloud to its dominant plane.

``align_point_cloud`` is the Open3D/NumPy equivalent of::

    plane, inliers = pcd.segment_plane(
        distance_threshold=0.02, ransac_n=3, num_iterations=2000
    )
    a, b, c, d = plane
    n = np.array([a, b, c])

It rotates the cloud so the plane normal (usually the floor) points along +Z and
writes ``aligned.ply`` next to the input. The COLMAP poses are not transformed.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import open3d as o3d

logger = logging.getLogger(__name__)

PLANE_DISTANCE_THRESHOLD = 0.02
PLANE_RANSAC_N = 3
PLANE_ITERATIONS = 2000
DEFAULT_OUTPUT_NAME = "aligned.ply"
UP_AXIS = (0.0, 0.0, 1.0)


def _skew(vector: "np.ndarray") -> "np.ndarray":
    x, y, z = vector
    return np.array(
        [
            [0.0, -z, y],
            [z, 0.0, -x],
            [-y, x, 0.0],
        ],
        dtype=float,
    )


def _rotation_from_to(source: "np.ndarray", target: "np.ndarray") -> "np.ndarray":
    """Rotation matrix that maps the unit vector ``source`` onto ``target``."""
    dot = float(np.clip(np.dot(source, target), -1.0, 1.0))
    if dot > 1.0 - 1e-9:
        return np.eye(3)
    if dot < -1.0 + 1e-9:
        axis = np.cross(source, [1.0, 0.0, 0.0])
        if np.linalg.norm(axis) < 1e-9:
            axis = np.cross(source, [0.0, 1.0, 0.0])
        axis = axis / np.linalg.norm(axis)
        return 2.0 * np.outer(axis, axis) - np.eye(3)

    axis = np.cross(source, target)
    axis = axis / np.linalg.norm(axis)
    angle = float(np.arccos(dot))
    skew = _skew(axis)
    return np.eye(3) + np.sin(angle) * skew + (1.0 - np.cos(angle)) * (skew @ skew)


def align_point_cloud(
    point_cloud_path: str | Path,
    output_path: str | Path | None = None,
    *,
    up_axis: tuple[float, float, float] = UP_AXIS,
) -> Path:
    """Segment the dominant plane and rotate the cloud so its normal is ``up_axis``.

    ``point_cloud_path`` is a PLY such as ``artifacts/v1/cleaned.ply``. The
    result is written to ``output_path`` (default: ``aligned.ply`` next to the
    input) and that path is returned.

    Raises ``FileNotFoundError`` when the input is missing, ``ValueError`` for a
    zero ``up_axis`` or an output that would overwrite the input, and
    ``RuntimeError`` when Open3D cannot read, segment, or write the cloud.
    """
    source = Path(point_cloud_path)
    if not source.is_file():
        raise FileNotFoundError(f"point cloud not found: {source}")

    output = (
        Path(output_path)
        if output_path is not None
        else source.with_name(DEFAULT_OUTPUT_NAME)
    )
    if output.resolve() == source.resolve():
        raise ValueError("output_path must differ from point_cloud_path")

    up = np.asarray(up_axis, dtype=float)
    if np.linalg.norm(up) < 1e-12:
        raise ValueError("up_axis must be a non-zero vector")
    up = up / np.linalg.norm(up)

    point_cloud = o3d.io.read_point_cloud(str(source))
    if point_cloud.is_empty():
        raise RuntimeError(f"could not read any points from {source}")
    if len(point_cloud.points) < PLANE_RANSAC_N:
        raise RuntimeError(
            f"need at least {PLANE_RANSAC_N} points to segment a plane, "
            f"{source} has {len(point_cloud.points)}"
        )

    plane, inliers = point_cloud.segment_plane(
        distance_threshold=PLANE_DISTANCE_THRESHOLD,
        ransac_n=PLANE_RANSAC_N,
        num_iterations=PLANE_ITERATIONS,
    )
    a, b, c, d = plane
    normal = np.array([a, b, c], dtype=float)
    length = np.linalg.norm(normal)
    if length < 1e-12:
        raise RuntimeError(f"plane segmentation returned a zero normal for {source}")
    normal = normal / length
    d = d / length

    if float(np.dot(normal, up)) < 0.0:
        normal = -normal
        d = -d

    rotation = _rotation_from_to(normal, up)
    point_cloud.rotate(rotation, center=(0.0, 0.0, 0.0))

    output.parent.mkdir(parents=True, exist_ok=True)
    if not o3d.io.write_point_cloud(str(output), point_cloud):
        raise RuntimeError(f"could not write aligned point cloud to {output}")

    logger.info(
        "aligned %s with plane (%0.4f, %0.4f, %0.4f, %0.4f), %d inliers -> %s",
        source,
        normal[0],
        normal[1],
        normal[2],
        d,
        len(inliers),
        output,
    )
    return output
