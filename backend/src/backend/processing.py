"""The "Process" stage: turn a session's raw photos and videos into the images
and frames the next stage can consume.

OpenCV does the work: photos are validated/re-encoded into ``processed/images``,
and videos are handed to ``pipeline()``, which uses ``extract_frames`` to write
blur-filtered stills into ``extracted_frames/``. From those frames it runs COLMAP
feature extraction and exhaustive matching (via ``feature_extraction`` and
``feature_matching``) into ``reconstruction/colmap/<run_id>/``. The job runs as an
asyncio task so the HTTP request that starts it returns immediately; each blocking
call is pushed to a worker thread so the event loop, and therefore uploads and SSE,
stay responsive.

The photo hand-off artifact is processed/inputs.json (the file the next stage
reads).

``pipeline(videos)`` is the single ownership point for the reconstruction work:
the job runner hands it every video in the session and treats its
``PIPELINE_DONE`` return value as the completion signal.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps
from sqlmodel import select

from .config import Settings
from .events import JOB_DONE, JOB_FAILED, JOB_PROGRESS, JOB_STARTED
from .extract_frames import extract_frames
from .feature_extraction import extract_features
from .feature_matching import match_features
from .models import READY, STORED, Asset, iso, utcnow

logger = logging.getLogger(__name__)

PROCESSED_DIRNAME = "processed"
IMAGES_DIRNAME = "images"
INPUTS_NAME = "inputs.json"
EXTRACTED_FRAMES_DIRNAME = "extracted_frames"
RECONSTRUCTION_DIRNAME = "reconstruction"
COLMAP_DIRNAME = "colmap"
COLMAP_DATABASE_NAME = "database.db"

# Sampling knobs for turning a photo into a normalized still. Bounded so a huge
# upload cannot tie up the worker for minutes.
MAX_IMAGE_DIM = 2000
JPEG_QUALITY = 90

JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_DONE_STATUS = "done"
JOB_FAILED_STATUS = "failed"
JOB_IDLE = "idle"

# The only return value pipeline() is allowed to produce. The job runner treats
# this as the "finished" signal and keys off nothing else.
PIPELINE_DONE = {"status": JOB_DONE_STATUS}

# Only fully stored assets are processed; an upload still in flight is picked up by
# the next run.
_PROCESSABLE = (STORED, READY)


@dataclass
class ProcessingJob:
    session_id: str
    status: str = JOB_QUEUED
    phase: str = ""
    done: int = 0
    total: int = 0
    image_count: int = 0
    message: str = ""
    output_dir: str = ""
    inputs_file: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None

    def snapshot(self) -> dict:
        return asdict(self)


def processed_dir(settings: Settings, session_id: str) -> Path:
    return settings.session_dir(session_id) / PROCESSED_DIRNAME


def extracted_frames_dir(settings: Settings, session_id: str) -> Path:
    return settings.session_dir(session_id) / EXTRACTED_FRAMES_DIRNAME


def colmap_run_dir(settings: Settings, session_id: str, run_id: str) -> Path:
    return (
        settings.session_dir(session_id)
        / RECONSTRUCTION_DIRNAME
        / COLMAP_DIRNAME
        / run_id
    )


async def _publish(app, session_id: str, event: str, job: ProcessingJob) -> None:
    await app.state.broker.publish(session_id, event, job.snapshot())


def _relative(settings: Settings, path: Path) -> str:
    """Paths are stored relative to DATA_DIR, like Asset.stored_path."""
    try:
        return path.relative_to(settings.data_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _fit(image: "np.ndarray") -> "np.ndarray":
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= MAX_IMAGE_DIM:
        return image
    scale = MAX_IMAGE_DIM / longest
    return cv2.resize(
        image,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )


def _imread_pillow(source: Path) -> "np.ndarray | None":
    """Fallback for formats OpenCV cannot decode (HEIC from iPhones, for example)."""
    try:
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            rgb = np.asarray(image.convert("RGB"))
    except Exception as exc:  # noqa: BLE001 - a bad photo must not fail the job
        logger.warning("could not read image %s: %s", source, exc)
        return None
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def process_photo(source: Path, images_dir: Path, stem: str) -> dict | None:
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        image = _imread_pillow(source)
    if image is None:
        return None
    dest = images_dir / f"{stem}.jpg"
    if not cv2.imwrite(str(dest), _fit(image), [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]):
        return None
    return {"image": dest.name, "frame_index": None}


class ProcessingManager:
    """One job per session, tracked on app.state. State is in memory only; the
    output on disk (inputs.json) is the durable record and lets a restarted API
    still report a completed run."""

    def __init__(self) -> None:
        self._jobs: dict[str, ProcessingJob] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def status(self, settings: Settings, session_id: str) -> dict:
        job = self._jobs.get(session_id)
        if job is not None:
            return job.snapshot()
        inputs = processed_dir(settings, session_id) / INPUTS_NAME
        if inputs.is_file():
            return self._completed_from_disk(settings, session_id, inputs)
        return ProcessingJob(session_id=session_id, status=JOB_IDLE).snapshot()

    async def start(self, app, session_id: str) -> dict:
        task = self._tasks.get(session_id)
        if task is not None and not task.done():
            return self._jobs[session_id].snapshot()

        settings: Settings = app.state.settings
        job = ProcessingJob(
            session_id=session_id,
            output_dir=_relative(settings, processed_dir(settings, session_id)),
        )
        self._jobs[session_id] = job
        self._tasks[session_id] = asyncio.create_task(self._run(app, session_id, job))
        return job.snapshot()

    async def _run(self, app, session_id: str, job: ProcessingJob) -> None:
        settings: Settings = app.state.settings
        job.status = JOB_RUNNING
        job.started_at = iso(utcnow())
        await _publish(app, session_id, JOB_STARTED, job)

        try:
            with app.state.database.session() as db:
                assets = db.exec(
                    select(Asset)
                    .where(Asset.session_id == session_id)
                    .where(Asset.status.in_(_PROCESSABLE))
                    .order_by(Asset.created_at)
                ).all()
                sources = [
                    {
                        "asset_id": asset.id,
                        "kind": asset.kind,
                        "original_filename": asset.original_filename,
                        "stored_path": asset.stored_path,
                        "mime": asset.mime,
                    }
                    for asset in assets
                    if asset.kind in ("photo", "video") and asset.stored_path
                ]

            out = processed_dir(settings, session_id)
            images_dir = out / IMAGES_DIRNAME
            if images_dir.exists():
                shutil.rmtree(images_dir)
            images_dir.mkdir(parents=True, exist_ok=True)

            job.total = len(sources)
            job.phase = "preparing"
            await _publish(app, session_id, JOB_PROGRESS, job)

            images: list[dict] = []
            for source in sources:
                job.phase = f"working on {source['original_filename'] or source['asset_id']}"
                await _publish(app, session_id, JOB_PROGRESS, job)
                path = settings.data_dir / source["stored_path"]
                if path.is_file():
                    images.extend(
                        await asyncio.to_thread(
                            _process_one, source, path, images_dir, len(sources) > 1
                        )
                    )
                job.done += 1
                job.image_count = len(images)
                await _publish(app, session_id, JOB_PROGRESS, job)

            # Owner hook: hand every video in this session to pipeline(). It runs
            # in a worker thread so a long run does not block the event loop, and
            # its return value must be the PIPELINE_DONE signal.
            videos = [source for source in sources if source["kind"] == "video"]
            job.phase = "pipeline"
            await _publish(app, session_id, JOB_PROGRESS, job)
            signal = await asyncio.to_thread(
                pipeline, videos, settings=settings, session_id=session_id
            )
            if signal.get("status") != JOB_DONE_STATUS:
                raise RuntimeError(f"pipeline reported {signal!r}, expected {PIPELINE_DONE!r}")

            payload = {
                "session_id": session_id,
                "generated_at": iso(utcnow()),
                "source_count": len(sources),
                "image_count": len(images),
                "sources": sources,
                "images": [
                    {
                        "path": _relative(settings, images_dir / record["image"]),
                        "source_asset_id": record["source_asset_id"],
                        "source_kind": record["source_kind"],
                        "source_filename": record["source_filename"],
                        "frame_index": record["frame_index"],
                    }
                    for record in images
                ],
            }
            inputs_file = out / INPUTS_NAME
            inputs_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            job.status = JOB_DONE_STATUS
            job.phase = "finished"
            job.image_count = len(images)
            job.inputs_file = _relative(settings, inputs_file)
            job.message = (
                f"{len(images)} images from {len(sources)} uploads"
                if sources
                else "nothing to process yet"
            )
            job.finished_at = iso(utcnow())
            await _publish(app, session_id, JOB_DONE, job)
        except Exception as exc:  # noqa: BLE001 - a failed job reports, it never crashes
            logger.exception("processing failed for session %s", session_id)
            job.status = JOB_FAILED_STATUS
            job.phase = "failed"
            job.error = str(exc)
            job.finished_at = iso(utcnow())
            await _publish(app, session_id, JOB_FAILED, job)

    def _completed_from_disk(self, settings: Settings, session_id: str, inputs: Path) -> dict:
        try:
            payload = json.loads(inputs.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ProcessingJob(session_id=session_id, status=JOB_IDLE).snapshot()
        job = ProcessingJob(
            session_id=session_id,
            status=JOB_DONE_STATUS,
            phase="finished",
            total=payload.get("source_count", 0),
            done=payload.get("source_count", 0),
            image_count=payload.get("image_count", 0),
            output_dir=_relative(settings, processed_dir(settings, session_id)),
            inputs_file=_relative(settings, inputs),
            finished_at=payload.get("generated_at"),
            message=f"{payload.get('image_count', 0)} images ready",
        )
        return job.snapshot()


def _process_one(source: dict, path: Path, images_dir: Path, indexed: bool) -> list[dict]:
    """Runs in a worker thread. Returns one record per produced image.

    Videos are not normalized here: they are handed to pipeline() and handled by
    extract_frames, so this returns nothing for them.
    """
    if source["kind"] == "video":
        return []

    stem = source["asset_id"] if indexed else Path(source["stored_path"]).stem
    photo = process_photo(path, images_dir, stem)
    if not photo:
        return []
    return [
        {
            **photo,
            "source_asset_id": source["asset_id"],
            "source_kind": source["kind"],
            "source_filename": source["original_filename"],
        }
    ]


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
    extraction and exhaustive matching over those frames in
    ``sessions/<session_id>/reconstruction/colmap/<run_id>/``. Extend this for the
    later stages (mapping, mesh/splat generation). The returned value is the
    job-completion signal and must stay exactly ``PIPELINE_DONE``; the job runner
    treats any other value as a failure.
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
    return PIPELINE_DONE
