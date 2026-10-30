"""Point-cloud cleaning for a frozen reconstruction.

``clean_point_cloud`` is the Open3D equivalent of::

    pcd = o3d.io.read_point_cloud("fused.ply")
    pcd, _ = pcd.remove_statistical_outlier(nb_neighbors=30, std_ratio=2.0)
    pcd, _ = pcd.remove_radius_outlier(nb_points=16, radius=0.05)  # COLMAP units
    pcd = pcd.voxel_down_sample(voxel_size=0.01)

The cleaned cloud is written next to the input as ``cleaned.ply`` by default.
"""

from __future__ import annotations

import logging
from pathlib import Path

import open3d as o3d

logger = logging.getLogger(__name__)

STATISTICAL_NEIGHBORS = 30
STATISTICAL_STD_RATIO = 2.0
RADIUS_POINTS = 16
RADIUS = 0.05
VOXEL_SIZE = 0.01
DEFAULT_OUTPUT_NAME = "cleaned.ply"


def clean_point_cloud(
    point_cloud_path: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    """Remove outliers and downsample a dense point cloud.

    ``point_cloud_path`` is a PLY such as ``artifacts/v1/fused.ply``. The result
    is written to ``output_path`` (default: ``cleaned.ply`` next to the input)
    and that path is returned.

    Raises ``FileNotFoundError`` when the input is missing, ``ValueError`` when
    the output would overwrite it, and ``RuntimeError`` when Open3D cannot read,
    clean, or write the cloud.
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

    point_cloud = o3d.io.read_point_cloud(str(source))
    if point_cloud.is_empty():
        raise RuntimeError(f"could not read any points from {source}")
    logger.info("cleaning %s (%d points)", source, len(point_cloud.points))

    point_cloud, _ = point_cloud.remove_statistical_outlier(
        nb_neighbors=STATISTICAL_NEIGHBORS,
        std_ratio=STATISTICAL_STD_RATIO,
    )
    point_cloud, _ = point_cloud.remove_radius_outlier(
        nb_points=RADIUS_POINTS,
        radius=RADIUS,
    )
    point_cloud = point_cloud.voxel_down_sample(voxel_size=VOXEL_SIZE)
    if point_cloud.is_empty():
        raise RuntimeError(f"cleaning removed every point from {source}")

    output.parent.mkdir(parents=True, exist_ok=True)
    if not o3d.io.write_point_cloud(str(output), point_cloud):
        raise RuntimeError(f"could not write cleaned point cloud to {output}")

    logger.info("wrote %d cleaned points to %s", len(point_cloud.points), output)
    return output
