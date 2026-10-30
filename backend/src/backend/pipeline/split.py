"""Split a reconstructed mesh into visual and collision variants.

``split_mesh`` is the Open3D equivalent of::

    # visual: keep detail
    visual = mesh

    # collision: aggressive
    col = mesh.simplify_quadric_decimation(target_number_of_triangles=15000)
    labels, counts, _ = col.cluster_connected_triangles()
    # drop clusters with < ~1% of triangles

The full-detail mesh is written as ``visual.ply`` and the simplified, cleaned
mesh as ``collision.ply``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import open3d as o3d

logger = logging.getLogger(__name__)

COLLISION_TRIANGLES = 15000
MIN_CLUSTER_FRACTION = 0.01
VISUAL_FILENAME = "visual.ply"
COLLISION_FILENAME = "collision.ply"


def split_mesh(
    mesh_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    collision_triangles: int = COLLISION_TRIANGLES,
    min_cluster_fraction: float = MIN_CLUSTER_FRACTION,
) -> tuple[Path, Path]:
    """Write full-detail and simplified collision meshes.

    ``mesh_path`` is a PLY such as ``artifacts/v1/mesh.ply``. ``visual.ply`` and
    ``collision.ply`` are written to ``output_dir`` (default: the input's
    directory), and their paths are returned in that order.

    Raises ``FileNotFoundError`` when the input is missing, ``ValueError`` for
    invalid parameters or an output that would overwrite the input, and
    ``RuntimeError`` when Open3D cannot read, simplify, or write the meshes.
    """
    source = Path(mesh_path)
    if not source.is_file():
        raise FileNotFoundError(f"mesh not found: {source}")
    if collision_triangles < 1:
        raise ValueError("collision_triangles must be at least 1")
    if not 0.0 <= min_cluster_fraction <= 1.0:
        raise ValueError("min_cluster_fraction must be between 0 and 1")

    output = Path(output_dir) if output_dir is not None else source.parent
    visual_path = output / VISUAL_FILENAME
    collision_path = output / COLLISION_FILENAME
    if source.resolve() in {visual_path.resolve(), collision_path.resolve()}:
        raise ValueError("output paths must differ from mesh_path")

    mesh = o3d.io.read_triangle_mesh(str(source))
    if mesh.is_empty():
        raise RuntimeError(f"could not read any triangles from {source}")
    if not mesh.has_vertex_normals():
        mesh.compute_vertex_normals()

    visual = mesh
    output.mkdir(parents=True, exist_ok=True)
    if not o3d.io.write_triangle_mesh(str(visual_path), visual):
        raise RuntimeError(f"could not write visual mesh to {visual_path}")

    logger.info(
        "simplifying %s from %d to %d triangles",
        source,
        len(mesh.triangles),
        collision_triangles,
    )
    collision = mesh.simplify_quadric_decimation(
        target_number_of_triangles=collision_triangles
    )
    if collision.is_empty():
        raise RuntimeError(f"mesh simplification produced no triangles for {source}")

    labels, counts, _ = collision.cluster_connected_triangles()
    labels = np.asarray(labels)
    counts = np.asarray(counts)
    total = len(collision.triangles)
    small_clusters = np.flatnonzero(counts < total * min_cluster_fraction)
    removed = 0
    if small_clusters.size:
        mask = np.isin(labels, small_clusters)
        removed = int(mask.sum())
        collision.remove_triangles_by_mask(mask)
        collision.remove_unreferenced_vertices()

    if collision.is_empty():
        raise RuntimeError(
            f"cluster filtering removed every triangle from the collision mesh "
            f"built from {source}"
        )
    collision.compute_vertex_normals()

    if not o3d.io.write_triangle_mesh(str(collision_path), collision):
        raise RuntimeError(f"could not write collision mesh to {collision_path}")

    logger.info(
        "wrote visual mesh (%d triangles) to %s and collision mesh "
        "(%d triangles, dropped %d small-cluster triangles) to %s",
        len(visual.triangles),
        visual_path,
        len(collision.triangles),
        removed,
        collision_path,
    )
    return visual_path, collision_path
