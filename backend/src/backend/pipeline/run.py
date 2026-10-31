"""Reconstruction pipeline orchestration.

``pipeline(videos)`` is the single ownership point for the reconstruction work.
The Process job hands it every video in the session and treats its
``PIPELINE_DONE`` return value as the completion signal.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter

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


def _fields(**values: object) -> str:
    return " ".join(f"{key}={value}" for key, value in values.items())


def _one_line(value: object) -> str:
    return str(value).replace("\r", " ").replace("\n", " ")


@contextmanager
def _stage(name: str, session_id: str, **fields: object) -> Iterator[None]:
    """Emit one parseable line for every stage start, finish, or failure."""
    started = perf_counter()
    details = f" {_fields(**fields)}" if fields else ""
    logger.info(
        "pipeline stage=%s status=start session=%s%s", name, session_id, details
    )
    try:
        yield
    except Exception as exc:
        elapsed_ms = int((perf_counter() - started) * 1000)
        logger.error(
            "pipeline stage=%s status=failed session=%s elapsed_ms=%d%s error=%s",
            name,
            session_id,
            elapsed_ms,
            details,
            _one_line(exc),
        )
        raise
    else:
        elapsed_ms = int((perf_counter() - started) * 1000)
        logger.info(
            "pipeline stage=%s status=ok session=%s elapsed_ms=%d%s",
            name,
            session_id,
            elapsed_ms,
            details,
        )


def _skipped(name: str, session_id: str, reason: str, **fields: object) -> None:
    details = f" {_fields(**fields)}" if fields else ""
    logger.warning(
        "pipeline stage=%s status=skipped session=%s reason=%s%s",
        name,
        session_id,
        reason,
        details,
    )


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
    with _stage("pipeline", session_id):
        frames_dir = extracted_frames_dir(settings, session_id)
        extracted = 0
        for video in videos:
            source = settings.data_dir / video["stored_path"]
            if not source.is_file():
                _skipped(
                    "frames",
                    session_id,
                    "video_missing",
                    asset_id=video["asset_id"],
                    path=source,
                )
                continue
            try:
                with _stage("frames", session_id, asset_id=video["asset_id"]):
                    extract_frames(source, frames_dir, prefix=video["asset_id"])
                extracted += 1
            except Exception as exc:  # noqa: BLE001 - one bad video must not fail the job
                logger.warning("frame extraction skipped for %s: %s", source, exc)

        if extracted == 0:
            _skipped("frames", session_id, "no_frames_extracted")
            return PIPELINE_DONE

        run_id = utcnow().strftime("%Y%m%dT%H%M%SZ")
        database_path = (
            colmap_run_dir(settings, session_id, run_id) / COLMAP_DATABASE_NAME
        )
        with _stage("features", session_id, run_id=run_id):
            extract_features(frames_dir, database_path)
        with _stage("matching", session_id, run_id=run_id):
            match_features(database_path)
        sparse_dir = database_path.parent / SPARSE_DIRNAME
        with _stage("mapping", session_id, run_id=run_id):
            run_mapper(database_path, frames_dir, sparse_dir)

        model_dirs = (
            sorted(path for path in sparse_dir.iterdir() if path.is_dir())
            if sparse_dir.is_dir()
            else []
        )
        if not model_dirs:
            _skipped("mapping", session_id, "no_sparse_models", run_id=run_id)

        frozen = False
        for model_dir in model_dirs:
            with _stage("analysis", session_id, model=model_dir.name):
                analyze_model(model_dir)

            dense_path = None
            if dense_available():
                with _stage("dense", session_id, model=model_dir.name):
                    dense_path = run_dense_reconstruction(
                        frames_dir,
                        model_dir,
                        database_path.parent / DENSE_DIRNAME / model_dir.name,
                    )
            else:
                _skipped("dense", session_id, "no_backend", model=model_dir.name)

            if dense_path is not None and not frozen:
                with _stage("freeze", session_id, model=model_dir.name):
                    artifact_dir = freeze_artifacts(
                        model_dir,
                        dense_path,
                        artifacts_dir(settings, session_id),
                    )
                with _stage("clean", session_id, model=model_dir.name):
                    cleaned_path = clean_point_cloud(
                        artifact_dir / POINT_CLOUD_FILENAME
                    )
                with _stage("align", session_id, model=model_dir.name):
                    aligned_path = align_point_cloud(cleaned_path)
                with _stage("mesh", session_id, model=model_dir.name):
                    mesh_path = reconstruct_mesh(aligned_path)
                with _stage("split", session_id, model=model_dir.name):
                    visual_path, collision_path = split_mesh(mesh_path)
                with _stage("export", session_id, model=model_dir.name):
                    export_models(visual_path, collision_path)
                frozen = True

        if not frozen:
            _skipped("artifacts", session_id, "no_dense_point_cloud")
        return PIPELINE_DONE
