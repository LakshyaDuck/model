"""The "Process" job: normalize photos and run the reconstruction pipeline.

Photos are validated/re-encoded into ``processed/images`` by
``pipeline.prepare``. Every video is handed to ``pipeline.run.pipeline()``, which
extracts frames and runs the reconstruction stages. ``processed/inputs.json`` is
the durable hand-off artifact. The job runs as an asyncio task so the HTTP request
that starts it returns immediately; each blocking call is pushed to a worker thread
so the event loop, and therefore uploads and SSE, stay responsive.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlmodel import select

from .config import Settings
from .events import JOB_DONE, JOB_FAILED, JOB_PROGRESS, JOB_STARTED
from .models import READY, STORED, Asset, iso, utcnow
from .pipeline import (
    COLLISION_FILENAME,
    PIPELINE_DONE,
    SCENE_FILENAME,
    artifacts_dir,
    images_dir,
    inputs_file,
    pipeline,
    prepare_asset,
    processed_dir,
    relative_to_data,
)

logger = logging.getLogger(__name__)

JOB_QUEUED = "queued"
JOB_RUNNING = "running"
# The job is done only when pipeline() returns its PIPELINE_DONE signal.
JOB_DONE_STATUS = PIPELINE_DONE["status"]
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
    model_path: str = ""
    collision_model_path: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None

    def snapshot(self) -> dict:
        return asdict(self)


async def _publish(app, session_id: str, event: str, job: ProcessingJob) -> None:
    await app.state.broker.publish(session_id, event, job.snapshot())


def _model_paths(settings: Settings, session_id: str) -> dict[str, str]:
    """Report GLBs relative to DATA_DIR; missing artifacts stay empty."""
    artifact = artifacts_dir(settings, session_id)
    paths = {"model_path": "", "collision_model_path": ""}
    for field, filename in (
        ("model_path", SCENE_FILENAME),
        ("collision_model_path", COLLISION_FILENAME),
    ):
        path = artifact / filename
        if path.is_file():
            paths[field] = relative_to_data(settings, path)
    return paths


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
        inputs = inputs_file(settings, session_id)
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
            output_dir=relative_to_data(settings, processed_dir(settings, session_id)),
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

            images_path = images_dir(settings, session_id)
            if images_path.exists():
                shutil.rmtree(images_path)
            images_path.mkdir(parents=True, exist_ok=True)

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
                            prepare_asset, source, path, images_path, len(sources) > 1
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
                        "path": relative_to_data(settings, images_path / record["image"]),
                        "source_asset_id": record["source_asset_id"],
                        "source_kind": record["source_kind"],
                        "source_filename": record["source_filename"],
                        "frame_index": record["frame_index"],
                    }
                    for record in images
                ],
            }
            inputs_path = inputs_file(settings, session_id)
            inputs_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            job.status = JOB_DONE_STATUS
            job.phase = "finished"
            job.image_count = len(images)
            job.inputs_file = relative_to_data(settings, inputs_path)
            for field, value in _model_paths(settings, session_id).items():
                setattr(job, field, value)
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
            output_dir=relative_to_data(settings, processed_dir(settings, session_id)),
            inputs_file=relative_to_data(settings, inputs),
            finished_at=payload.get("generated_at"),
            message=f"{payload.get('image_count', 0)} images ready",
            **_model_paths(settings, session_id),
        )
        return job.snapshot()
