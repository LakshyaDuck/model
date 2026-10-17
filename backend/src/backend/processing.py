"""The "Process" stage: turn a session's raw photos and videos into one normalized
set of images the next stage can consume.

OpenCV does the work (photos are validated/re-encoded, videos are decoded into a
sampled frame sequence). The job runs as an asyncio task so the HTTP request that
starts it returns immediately; each blocking call is pushed to a worker thread so
the event loop, and therefore uploads and SSE, stay responsive.

Everything is written under sessions/<id>/processed/ and the hand-off artifact is
processed/inputs.json (the file the next stage reads).
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
from .models import READY, STORED, Asset, iso, utcnow

logger = logging.getLogger(__name__)

PROCESSED_DIRNAME = "processed"
IMAGES_DIRNAME = "images"
INPUTS_NAME = "inputs.json"

# Sampling knobs for turning a video into stills. Bounded so a long upload cannot
# flood the output directory or tie up the worker for minutes.
TARGET_FPS = 2.0
MAX_FRAMES_PER_VIDEO = 300
MAX_IMAGE_DIM = 2000
JPEG_QUALITY = 90

JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_DONE_STATUS = "done"
JOB_FAILED_STATUS = "failed"
JOB_IDLE = "idle"

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


def process_video(source: Path, images_dir: Path, stem: str) -> list[dict]:
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        logger.warning("could not open video %s", source)
        return []

    records: list[dict] = []
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        step = max(1, round((fps if fps and fps > 0 else 30.0) / TARGET_FPS))
        index = 0
        while len(records) < MAX_FRAMES_PER_VIDEO:
            ok, frame = cap.read()
            if not ok:
                break
            if index % step == 0:
                dest = images_dir / f"{stem}_f{len(records):04d}.jpg"
                if cv2.imwrite(
                    str(dest), _fit(frame), [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
                ):
                    records.append({"image": dest.name, "frame_index": index})
            index += 1
    finally:
        cap.release()
    return records


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
    """Runs in a worker thread. Returns one record per produced image."""
    stem = source["asset_id"] if indexed else Path(source["stored_path"]).stem
    if source["kind"] == "video":
        produced = [
            {"image": r["image"], "frame_index": r["frame_index"]}
            for r in process_video(path, images_dir, stem)
        ]
    else:
        photo = process_photo(path, images_dir, stem)
        produced = [photo] if photo else []
    source_kind = source["kind"]
    return [
        {
            **record,
            "source_asset_id": source["asset_id"],
            "source_kind": source_kind,
            "source_filename": source["original_filename"],
        }
        for record in produced
    ]
