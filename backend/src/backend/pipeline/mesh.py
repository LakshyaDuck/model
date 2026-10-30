"""Poisson surface reconstruction for an aligned point cloud.

``reconstruct_mesh`` is the Open3D equivalent of::

    mesh, dens = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pcd, depth=9
    )
    dens = np.asarray(dens)
    mesh.remove_vertices_by_mask(dens < np.quantile(dens, 0.05))

It writes ``mesh.ply`` next to the input. Clouds without normals get estimated,
consistently oriented normals before reconstruction.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import open3d as o3d

logger = logging.getLogger(__name__)

POISSON_DEPTH = 9
DENSITY_QUANTILE = 0.05
DEFAULT_OUTPUT_NAME = "mesh.ply"


def reconstruct_mesh(
    point_cloud_path: str | Path,
    output_path: str | Path | None = None,
    *,
    depth: int = POISSON_DEPTH,
    density_quantile: float = DENSITY_QUANTILE,
) -> Path:
    """Build a triangle mesh from a point cloud with Poisson reconstruction.

    ``point_cloud_path`` is a PLY such as ``artifacts/v1/aligned.ply``. The mesh
    is written to ``output_path`` (default: ``mesh.ply`` next to the input) and
    that path is returned.

    Raises ``FileNotFoundError`` when the input is missing, ``ValueError`` for
    invalid parameters or an output that would overwrite the input, and
    ``RuntimeError`` when Open3D cannot read, reconstruct, or write the mesh.
    """
    source = Path(point_cloud_path)
    if not source.is_file():
        raise FileNotFoundError(f"point cloud not found: {source}")
    if depth < 1:
        raise ValueError("depth must be at least 1")
    if not 0.0 <= density_quantile <= 1.0:
        raise ValueError("density_quantile must be between 0 and 1")

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
    if not point_cloud.has_normals():
        logger.info("estimating normals for %s", source)
        point_cloud.estimate_normals()
        point_cloud.orient_normals_consistent_tangent_plane(30)

    logger.info(
        "running Poisson reconstruction on %s (%d points, depth=%d)",
        source,
        len(point_cloud.points),
        depth,
    )
    try:
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            point_cloud,
            depth=depth,
        )
    except Exception as exc:  # noqa: BLE001 - surface Open3D's reason
        raise RuntimeError(
            f"Poisson reconstruction failed for {source}: {exc}"
        ) from exc

    densities = np.asarray(densities)
    if densities.size == 0:
        raise RuntimeError(
            f"Poisson reconstruction produced no densities for {source}"
        )

    vertices_before = len(mesh.vertices)
    threshold = float(np.quantile(densities, density_quantile))
    mesh.remove_vertices_by_mask(densities < threshold)
    if mesh.is_empty():
        raise RuntimeError(
            f"density filtering removed every vertex from the mesh built from {source}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    if not o3d.io.write_triangle_mesh(str(output), mesh):
        raise RuntimeError(f"could not write mesh to {output}")

    logger.info(
        "wrote mesh with %d vertices and %d triangles to %s "
        "(removed %d low-density vertices below %0.4f)",
        len(mesh.vertices),
        len(mesh.triangles),
        output,
        vertices_before - len(mesh.vertices),
        threshold,
    )
    return output
