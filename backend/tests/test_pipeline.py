"""Tests for the pipeline's local-only pieces.

External binaries (ffmpeg, COLMAP, OpenMVS) need integration runs; these keep the
path helpers, photo preparation, and Open3D stages fast and deterministic.
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
import open3d as o3d
import trimesh

from backend.pipeline import (
    PIPELINE_DONE,
    align_point_cloud,
    artifacts_dir,
    colmap_run_dir,
    export_models,
    extracted_frames_dir,
    images_dir,
    inputs_file,
    pipeline,
    prepare_asset,
    process_photo,
    processed_dir,
    relative_to_data,
    split_mesh,
)


def test_path_helpers_match_session_layout(settings):
    session_id = "session-1"
    root = settings.session_dir(session_id)

    assert processed_dir(settings, session_id) == root / "processed"
    assert images_dir(settings, session_id) == root / "processed" / "images"
    assert inputs_file(settings, session_id) == root / "processed" / "inputs.json"
    assert extracted_frames_dir(settings, session_id) == root / "extracted_frames"
    assert (
        colmap_run_dir(settings, session_id, "run")
        == root / "reconstruction" / "colmap" / "run"
    )
    assert artifacts_dir(settings, session_id) == root / "artifacts" / "v1"
    assert relative_to_data(settings, root) == f"sessions/{session_id}"
    assert relative_to_data(settings, Path("/tmp/elsewhere")) == "/tmp/elsewhere"


def test_process_photo_fits_long_edge(tmp_path):
    source = tmp_path / "wide.png"
    assert cv2.imwrite(str(source), np.full((1000, 3000, 3), 127, dtype=np.uint8))

    output = tmp_path / "images"
    output.mkdir()
    assert process_photo(source, output, "wide") == {
        "image": "wide.jpg",
        "frame_index": None,
    }

    written = cv2.imread(str(output / "wide.jpg"))
    assert max(written.shape[:2]) == 2000
    assert written.shape[:2] == (667, 2000)


def test_prepare_asset_skips_videos(tmp_path):
    source = {
        "asset_id": "video-1",
        "kind": "video",
        "original_filename": "clip.mp4",
        "stored_path": "sessions/s/raw/video-1.mp4",
    }
    assert prepare_asset(source, tmp_path / "missing.mp4", tmp_path, False) == []


def test_prepare_asset_uses_asset_id_when_indexed(tmp_path):
    source_path = tmp_path / "original.jpg"
    assert cv2.imwrite(str(source_path), np.zeros((8, 8, 3), dtype=np.uint8))
    output = tmp_path / "images"
    output.mkdir()
    source = {
        "asset_id": "asset-1",
        "kind": "photo",
        "original_filename": "original.jpg",
        "stored_path": "sessions/s/raw/asset-1.jpg",
    }

    assert prepare_asset(source, source_path, output, indexed=True) == [
        {
            "image": "asset-1.jpg",
            "frame_index": None,
            "source_asset_id": "asset-1",
            "source_kind": "photo",
            "source_filename": "original.jpg",
        }
    ]


def test_pipeline_without_videos_returns_done(settings):
    assert PIPELINE_DONE == {"status": "done"}
    assert pipeline([], settings=settings, session_id="empty") == PIPELINE_DONE


def test_split_mesh_removes_disconnected_specks(tmp_path):
    sphere = o3d.geometry.TriangleMesh.create_sphere(radius=1.0, resolution=10)
    sphere.compute_vertex_normals()

    speck = o3d.geometry.TriangleMesh()
    speck.vertices = o3d.utility.Vector3dVector(
        np.array([[5.0, 0.0, 0.0], [5.2, 0.0, 0.0], [5.0, 0.2, 0.0]])
    )
    speck.triangles = o3d.utility.Vector3iVector(np.array([[0, 1, 2]]))
    speck.compute_vertex_normals()

    combined = sphere + speck
    source = tmp_path / "mesh.ply"
    assert o3d.io.write_triangle_mesh(str(source), combined)

    output = tmp_path / "artifacts"
    visual, collision = split_mesh(source, output)

    visual_mesh = o3d.io.read_triangle_mesh(str(visual))
    collision_mesh = o3d.io.read_triangle_mesh(str(collision))
    assert len(visual_mesh.triangles) == len(combined.triangles)
    assert len(collision_mesh.triangles) == len(sphere.triangles)
    assert visual == output / "visual.ply"
    assert collision == output / "collision.ply"


def test_export_models_writes_scene_and_collision_glb(tmp_path):
    visual = o3d.geometry.TriangleMesh.create_box()
    visual.compute_vertex_normals()
    visual.vertex_colors = o3d.utility.Vector3dVector(
        np.tile(np.array([[0.2, 0.4, 0.6]]), (len(visual.vertices), 1))
    )
    collision = o3d.geometry.TriangleMesh.create_box()
    collision.compute_vertex_normals()

    output = tmp_path / "artifacts"
    output.mkdir()
    visual_path = output / "visual.ply"
    collision_path = output / "collision.ply"
    assert o3d.io.write_triangle_mesh(str(visual_path), visual)
    assert o3d.io.write_triangle_mesh(str(collision_path), collision)

    scene_path, collision_glb = export_models(visual_path, collision_path)
    assert scene_path == output / "scene.glb"
    assert collision_glb == output / "collision.glb"
    assert scene_path.is_file()
    assert collision_glb.is_file()

    scene = trimesh.load(scene_path, force="mesh")
    exported_collision = trimesh.load(collision_glb, force="mesh")
    assert len(scene.vertices) == len(visual.vertices)
    assert len(scene.faces) == len(visual.triangles)
    assert len(exported_collision.faces) == len(collision.triangles)
    colors = np.asarray(scene.visual.vertex_colors)
    assert colors.shape[0] == len(visual.vertices)
    assert np.allclose(colors[0, :3], [51, 102, 153], atol=1)


def test_align_point_cloud_makes_dominant_plane_up(tmp_path):
    rng = np.random.default_rng(0)
    xy = rng.uniform(-1.0, 1.0, size=(2000, 2))
    z = 0.3 * xy[:, 0] + 0.2 * xy[:, 1] + 0.001 * rng.normal(size=2000)

    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.column_stack([xy, z]))
    source = tmp_path / "cleaned.ply"
    assert o3d.io.write_point_cloud(str(source), cloud)

    output = align_point_cloud(source)
    aligned = o3d.io.read_point_cloud(str(output))
    plane, _ = aligned.segment_plane(
        distance_threshold=0.02, ransac_n=3, num_iterations=2000
    )
    normal = np.asarray(plane[:3], dtype=float)
    normal /= np.linalg.norm(normal)

    assert output == tmp_path / "aligned.ply"
    assert normal[2] > 0.99


def test_pipeline_emits_stage_logs(settings):
    messages: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record):
            messages.append(record.getMessage())

    capture = Capture()
    logger = logging.getLogger("backend.pipeline.run")
    previous_level = logger.level
    previous_propagate = logger.propagate
    logger.addHandler(capture)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        assert pipeline([], settings=settings, session_id="session-logs") == PIPELINE_DONE
    finally:
        logger.removeHandler(capture)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate

    lines = "\n".join(messages)
    assert "pipeline stage=pipeline status=start session=session-logs" in lines
    assert (
        "pipeline stage=frames status=skipped session=session-logs "
        "reason=no_frames_extracted"
    ) in lines
    assert "pipeline stage=pipeline status=ok session=session-logs" in lines
