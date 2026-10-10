"""tusd HTTP hook endpoint (POST /internal/tusd-hook).

Payload and response shapes follow the official tusd hooks docs:
https://tus.github.io/tusd/advanced-topics/hooks

Three properties of the real tusd shape the code below:
  * tusd sends no secret header of its own, so HOOK_SECRET may arrive either as the
    X-Hook-Secret header (injected by your reverse proxy) or as ?secret= in the
    -hooks-http URL you configure.
  * any non-2XX from this endpoint is an *internal error* to tusd: it retries and
    answers 500 to the phone. Rejections are therefore reported as HTTP 200 with
    RejectUpload + HTTPResponse in the body.
  * ChangeFileInfo.MetaData REPLACES the upload metadata (pkg/handler), so we echo
    the client's keys back together with the ones we add.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException, Query, Request
from sqlmodel import select
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .events import CREATED, FAILED, READY, REMOVED, STORED
from .manifest import write_manifest
from .media import make_thumbnail, safe_suffix, sha256_file
from .models import FAILED as FAILED_STATUS
from .models import READY as READY_STATUS
from .models import STORED as STORED_STATUS
from .models import UPLOADING, Asset, KINDS, asset_json
from .security import session_for_pair_token, secret_ok

logger = logging.getLogger(__name__)

HOOK_SECRET_HEADER = "X-Hook-Secret"
REQUIRED_META = ("pair_token", "kind", "filename", "filetype")

router = APIRouter(prefix="/internal", tags=["internal"])


def _reject(status_code: int, message: str) -> dict[str, Any]:
    return {
        "HTTPResponse": {
            "StatusCode": status_code,
            "Body": json.dumps({"message": message}),
            "Header": {"Content-Type": "application/json"},
        },
        "RejectUpload": True,
    }


async def _publish(app, session_id: str, event: str, payload: dict) -> None:
    await app.state.broker.publish(session_id, event, payload)


def _fail(db, settings: Settings, asset_id: str, session_id: str, reason: str) -> None:
    asset = db.get(Asset, asset_id)
    if asset is None:
        return
    asset.status = FAILED_STATUS
    asset.error_reason = reason[:500]
    db.commit()
    write_manifest(db, settings, session_id)


@router.post("/tusd-hook", include_in_schema=False)
async def tusd_hook(
    request: Request,
    payload: dict[str, Any] = Body(...),
    secret: str | None = Query(default=None),
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    if not secret_ok(request.headers.get(HOOK_SECRET_HEADER) or secret, settings.hook_secret):
        raise HTTPException(status_code=401, detail="invalid hook secret")

    hook_type = str(payload.get("Type") or "")
    upload = (payload.get("Event") or {}).get("Upload") or {}
    meta = {str(k): str(v) for k, v in (upload.get("MetaData") or {}).items()}
    handler = HANDLERS.get(hook_type)
    if handler is None:
        logger.info("ignoring hook %s for upload %s", hook_type, upload.get("ID"))
        return {}
    return await handler(request.app, upload, meta)


async def pre_create(app, upload: dict, meta: dict[str, str]) -> dict[str, Any]:
    settings: Settings = app.state.settings
    missing = [key for key in REQUIRED_META if not meta.get(key)]
    if missing:
        return _reject(400, f"missing upload metadata: {', '.join(missing)}")

    kind = meta["kind"]
    if kind not in KINDS:
        return _reject(400, f"unknown kind {kind!r}, expected one of {sorted(KINDS)}")

    with app.state.database.session() as db:
        capture, reason = session_for_pair_token(db, meta["pair_token"])
        if capture is None:
            return _reject(403, f"pair token {reason}")

        size = int(upload.get("Size") or 0)
        if size > settings.max_upload_bytes:
            return _reject(413, f"file is {size} bytes, limit is {settings.max_upload_bytes}")

        existing = db.exec(select(Asset.id).where(Asset.session_id == capture.id)).all()
        if len(existing) >= settings.max_assets_per_session:
            return _reject(
                409,
                f"session already has {len(existing)} assets "
                f"(limit {settings.max_assets_per_session})",
            )
        session_id, asset_id = capture.id, uuid4().hex

    # session_id/asset_id are handed to every later hook through the metadata, so a
    # pair token that expires or gets re-issued mid-upload cannot orphan the upload.
    return {"ChangeFileInfo": {"MetaData": {**meta, "session_id": session_id, "asset_id": asset_id}}}


async def post_create(app, upload: dict, meta: dict[str, str]) -> dict[str, Any]:
    settings: Settings = app.state.settings
    session_id, asset_id = meta.get("session_id"), meta.get("asset_id")
    tus_id = str(upload.get("ID") or "")
    if not session_id or not asset_id:
        logger.warning("post-create for %s without pre-create metadata", tus_id)
        return {}

    created = False
    with app.state.database.session() as db:
        asset = db.get(Asset, asset_id)
        if asset is None:
            asset = Asset(
                id=asset_id,
                session_id=session_id,
                kind=meta.get("kind", ""),
                original_filename=meta.get("filename", ""),
                mime=meta.get("filetype", ""),
                size_bytes=int(upload.get("Size") or 0),
                status=UPLOADING,
                tus_upload_id=tus_id or None,
            )
            db.add(asset)
            db.commit()
            created = True
        elif tus_id and not asset.tus_upload_id:
            # post-finish can overtake post-create over HTTP; do not reset the status.
            asset.tus_upload_id = tus_id
            db.commit()
        if created:
            write_manifest(db, settings, session_id)
    if created:
        await _publish(app, session_id, CREATED, asset_json(asset))
    return {}


async def post_finish(app, upload: dict, meta: dict[str, str]) -> dict[str, Any]:
    session_id, asset_id = meta.get("session_id"), meta.get("asset_id")
    if not session_id or not asset_id:
        logger.warning("post-finish for %s without pre-create metadata", upload.get("ID"))
        return {}
    try:
        return await _store(app, upload, meta, session_id, asset_id)
    except Exception as exc:  # noqa: BLE001 - a bad file must not retry forever
        logger.exception("post-finish failed for asset %s", asset_id)
        settings: Settings = app.state.settings
        with app.state.database.session() as db:
            _fail(db, settings, asset_id, session_id, f"{type(exc).__name__}: {exc}")
        return {}


async def _store(app, upload: dict, meta: dict[str, str], session_id: str, asset_id: str) -> dict[str, Any]:
    settings: Settings = app.state.settings
    storage = upload.get("Storage") or {}
    source = Path(str(storage.get("Path") or ""))

    with app.state.database.session() as db:
        asset = db.get(Asset, asset_id)
        if asset is None:
            # post-finish is not guaranteed to arrive after post-create, and the
            # metadata carries everything needed to record the asset ourselves.
            asset = Asset(
                id=asset_id,
                session_id=session_id,
                kind=meta.get("kind", ""),
                original_filename=meta.get("filename", ""),
                mime=meta.get("filetype", ""),
                size_bytes=int(upload.get("Size") or 0),
                status=UPLOADING,
            )
            db.add(asset)
            db.commit()
            await _publish(app, session_id, CREATED, asset_json(asset))
        # tusd retries hooks, so an already-stored asset is a no-op.
        elif asset.stored_path and (settings.data_dir / asset.stored_path).exists():
            return {}
        if asset.status == FAILED_STATUS:
            return {}

        if int(upload.get("Size") or 0) > settings.max_upload_bytes:
            _fail(db, settings, asset_id, session_id, "upload exceeded MAX_UPLOAD_BYTES")
            await _publish(app, session_id, FAILED, asset_json(asset))
            return {}

        raw_dir = settings.session_dir(session_id) / "raw"
        thumb_dir = settings.session_dir(session_id) / "thumbs"
        raw_dir.mkdir(parents=True, exist_ok=True)
        thumb_dir.mkdir(parents=True, exist_ok=True)
        dest = raw_dir / f"{asset_id}{safe_suffix(asset.original_filename, asset.mime)}"

        if source.is_file():
            os.replace(source, dest)  # DATA_DIR/tus and DATA_DIR/sessions share a volume
        elif not dest.is_file():
            raise FileNotFoundError(f"uploaded data not found at {source}")

        if upload.get("ID"):
            asset.tus_upload_id = str(upload["ID"])
        asset.stored_path = str(dest.relative_to(settings.data_dir))
        asset.size_bytes = dest.stat().st_size
        asset.sha256 = await run_in_threadpool(sha256_file, dest)
        asset.status = STORED_STATUS
        asset.error_reason = None
        db.commit()
        write_manifest(db, settings, session_id)
        await _publish(app, session_id, STORED, asset_json(asset))

        thumb = await run_in_threadpool(
            make_thumbnail, dest, thumb_dir / f"{asset_id}.jpg", asset.mime, asset.kind
        )
        if thumb is not None:
            asset.thumb_path = str(thumb.relative_to(settings.data_dir))
        # A file without a thumbnail is still usable, so it counts as ready.
        asset.status = READY_STATUS
        db.commit()
        write_manifest(db, settings, session_id)
        await _publish(app, session_id, READY, asset_json(asset))
    return {}


async def post_terminate(app, upload: dict, meta: dict[str, str]) -> dict[str, Any]:
    settings: Settings = app.state.settings
    tus_id = str(upload.get("ID") or "")
    if not tus_id:
        return {}
    with app.state.database.session() as db:
        asset = db.exec(select(Asset).where(Asset.tus_upload_id == tus_id)).first()
        if asset is None:
            logger.info("post-terminate for unknown upload %s", tus_id)
            return {}
        asset_id, session_id = asset.id, asset.session_id
        for relative in (asset.stored_path, asset.thumb_path):
            if relative:
                (settings.data_dir / relative).unlink(missing_ok=True)
        db.delete(asset)
        db.commit()
        write_manifest(db, settings, session_id)
    await _publish(app, session_id, REMOVED, {"id": asset_id, "session_id": session_id})
    return {}


HANDLERS = {
    "pre-create": pre_create,
    "post-create": post_create,
    "post-finish": post_finish,
    "post-terminate": post_terminate,
}