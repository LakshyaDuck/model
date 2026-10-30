"""Export split meshes as web-ready GLB files.

``export_models`` reads ``visual.ply`` and ``collision.ply``, writes
``scene.glb`` (the full-detail visual mesh, including vertex colours when the PLY
has them) and ``collision.glb`` (the simplified collision mesh).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import open3d as o3d
import trimesh

logger = logging.getLogger(__name__)

SCENE_FILENAME = "scene.glb"
COLLISION_FILENAME = "collision.glb"


def _read_mesh(path: Path) -> o3d.geometry.TriangleMesh:
    mesh = o3d.io.read_triangle_mesh(str(path))
    if mesh.is_empty():
        raise RuntimeError(f"could not read any triangles from {path}")
    return mesh


def _trimesh_from_o3d(
    mesh: o3d.geometry.TriangleMesh, *, include_colors: bool
) -> trimesh.Trimesh:
    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.triangles)
    options = {}
    if include_colors and mesh.has_vertex_colors():
        colors = np.asarray(mesh.vertex_colors)
        if colors.size:
            options["vertex_colors"] = (
                np.clip(colors, 0.0, 1.0) * 255
            ).astype(np.uint8)
    return trimesh.Trimesh(
        vertices=vertices,
        faces=faces,
        process=False,
        **options,
    )


def export_models(
    visual_path: str | Path,
    collision_path: str | Path,
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write ``scene.glb`` and ``collision.glb``.

    ``visual_path`` and ``collision_path`` are the PLYs produced by
    ``split_mesh``. By default the GLBs are written next to their source meshes;
    ``output_dir`` puts both in the same directory. The returned paths are
    ``(scene.glb, collision.glb)``.

    Raises ``FileNotFoundError`` when either input is missing, ``RuntimeError``
    when a mesh is unreadable, and ``ValueError`` when an output would overwrite
    an input.
    """
    visual = Path(visual_path)
    collision = Path(collision_path)
    for source in (visual, collision):
        if not source.is_file():
            raise FileNotFoundError(f"mesh not found: {source}")

    if output_dir is not None:
        scene_path = Path(output_dir) / SCENE_FILENAME
        collision_glb_path = Path(output_dir) / COLLISION_FILENAME
    else:
        scene_path = visual.with_name(SCENE_FILENAME)
        collision_glb_path = collision.with_name(COLLISION_FILENAME)

    for output in (scene_path, collision_glb_path):
        if output.resolve() in {visual.resolve(), collision.resolve()}:
            raise ValueError("output paths must differ from input meshes")

    scene_path.parent.mkdir(parents=True, exist_ok=True)
    collision_glb_path.parent.mkdir(parents=True, exist_ok=True)

    scene = _trimesh_from_o3d(_read_mesh(visual), include_colors=True)
    collision_mesh = _trimesh_from_o3d(_read_mesh(collision), include_colors=False)

    scene.export(str(scene_path))
    collision_mesh.export(str(collision_glb_path))

    logger.info(
        "exported %d visual triangles to %s and %d collision triangles to %s",
        len(scene.faces),
        scene_path,
        len(collision_mesh.faces),
        collision_glb_path,
    )
    return scene_path, collision_glb_path
