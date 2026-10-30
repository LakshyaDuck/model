"""Reconstruction pipeline orchestration.

``pipeline(videos)`` is the single ownership point for the reconstruction work.
The Process job hands it every video in the session and treats its
``PIPELINE_DONE`` return value as the completion signal.
"""

from __future__ import annotations

import logging

from ..config import Settings
from ..models import utcnow
from .align import align_point_cloud
from .clean_point_cloud import clean_point_cloud
from .dense_reconstruction import dense_available, run_dense_reconstruction
from .export import export_models
from .extract_frames import extract_frames
from .feature_extraction import extract_features
from .feature_matching import match_features
from .freeze import POINT_CLOUD_FILENAME, freeze_artifacts
from .mapper import run_mapper
from .mesh import reconstruct_mesh
from .model_analyzer import analyze_model
from .paths import (
    COLMAP_DATABASE_NAME,
    DENSE_DIRNAME,
    SPARSE_DIRNAME,
    artifacts_dir,
    colmap_run_dir,
    extracted_frames_dir,
)
from .split import split_mesh

logger = logging.getLogger(__name__)

# The only return value pipeline() is allowed to produce. The job runner treats
# this as the "finished" signal and keys off nothing else.
PIPELINE_DONE = {"status": "done"}


def pipeline(videos: list[dict], *, settings: Settings, session_id: str) -> dict:
    """Process every video belonging to the current session.

    This is the single ownership point for the reconstruction work. `videos` is
    the session's uploaded videos in creation order, one dict per asset::

        {
            "asset_id": str,
            "kind": "video",
            "original_filename": str,
            "stored_path": str,  # relative to DATA_DIR
            "mime": str,
        }

    The default implementation extracts sharp frames from every video into
    ``sessions/<session_id>/extracted_frames/``, then runs COLMAP feature
    extraction, exhaustive matching, and incremental mapping over those frames in
    ``sessions/<session_id>/reconstruction/colmap/<run_id>/`` (the sparse model
    lands in ``sparse/``). Each produced model is then analyzed for its statistics
    and turned into a dense point cloud: COLMAP patch-match stereo when the
    ``pycolmap`` build has CUDA, otherwise OpenMVS on the CPU. The dense result is
    written under ``dense/<model_id>/`` (``fused.ply`` for COLMAP,
    ``scene_dense.ply`` for OpenMVS). The first model with a dense point cloud is
    frozen into ``artifacts/v1/`` as ``fused.ply`` plus a ``poses/`` text export,
    cleaned into ``artifacts/v1/cleaned.ply``, aligned to its dominant plane as
    ``artifacts/v1/aligned.ply``, meshed into ``artifacts/v1/mesh.ply``, split
    into ``artifacts/v1/visual.ply`` and ``artifacts/v1/collision.ply``, and
    exported as ``artifacts/v1/scene.glb`` and ``artifacts/v1/collision.glb``.
    The dense stage is skipped with a warning only when neither backend is
    available. Extend this for the later stages (texturing/splat generation). The
    returned value is the job-completion signal and must stay exactly
    ``PIPELINE_DONE``; the job runner treats any other value as a failure.
    """
    frames_dir = extracted_frames_dir(settings, session_id)
    extracted = 0
    for video in videos:
        source = settings.data_dir / video["stored_path"]
        if not source.is_file():
            logger.warning("video missing on disk, skipping: %s", source)
            continue
        try:
            extract_frames(source, frames_dir, prefix=video["asset_id"])
            extracted += 1
        except Exception as exc:  # noqa: BLE001 - one bad video must not fail the job
            logger.warning("frame extraction skipped for %s: %s", source, exc)

    if extracted == 0:
        logger.info("no frames extracted; skipping COLMAP for session %s", session_id)
        return PIPELINE_DONE

    run_id = utcnow().strftime("%Y%m%dT%H%M%SZ")
    database_path = colmap_run_dir(settings, session_id, run_id) / COLMAP_DATABASE_NAME
    extract_features(frames_dir, database_path)
    match_features(database_path)
    sparse_dir = database_path.parent / SPARSE_DIRNAME
    run_mapper(database_path, frames_dir, sparse_dir)
    frozen = False
    for model_dir in sorted(path for path in sparse_dir.iterdir() if path.is_dir()):
        analyze_model(model_dir)
        dense_path = None
        if dense_available():
            dense_path = run_dense_reconstruction(
                frames_dir,
                model_dir,
                database_path.parent / DENSE_DIRNAME / model_dir.name,
            )
        else:
            logger.warning(
                "dense reconstruction skipped for %s: no CUDA-enabled pycolmap "
                "and no OpenMVS tools on PATH",
                model_dir,
            )
        if dense_path is not None and not frozen:
            artifact_dir = freeze_artifacts(
                model_dir,
                dense_path,
                artifacts_dir(settings, session_id),
            )
            cleaned_path = clean_point_cloud(artifact_dir / POINT_CLOUD_FILENAME)
            aligned_path = align_point_cloud(cleaned_path)
            mesh_path = reconstruct_mesh(aligned_path)
            visual_path, collision_path = split_mesh(mesh_path)
            export_models(visual_path, collision_path)
            frozen = True

    if not frozen:
        logger.warning(
            "artifacts not frozen for session %s: no dense point cloud was produced",
            session_id,
        )
    return PIPELINE_DONE
