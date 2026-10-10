"""Public HTTP API. Everything except POST /api/sessions needs the owner token."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlmodel import select
from sse_starlette.sse import EventSourceResponse

from .config import Settings
from .events import KEEPALIVE_SECONDS, SNAPSHOT
from .manifest import manifest_payload, write_manifest
from .models import Asset, CaptureSession, iso, utcnow
from .security import (
    PAIR_EXPIRED,
    bearer_token,
    new_token,
    session_for_owner,
    session_for_pair_token,
    token_hash,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def require_owner(allow_query_token: bool = False):
    """Owner-token dependency.

    EventSource and <video>/<img> tags cannot set headers, so the two endpoints they
    need (events, file/thumb) also accept ?token=.
    """

    async def dependency(
        request: Request,
        token: str | None = Query(default=None),
    ) -> CaptureSession:
        token = bearer_token(request.headers.get("authorization")) or (
            token if allow_query_token else None
        )
        session_id = request.path_params["session_id"]
        with request.app.state.database.session() as db:
            capture = session_for_owner(db, session_id, token)
        if capture is None:
            raise HTTPException(status_code=401, detail="invalid owner token")
        return capture

    return dependency


def _new_pair_expiry(settings: Settings):
    return utcnow() + timedelta(minutes=settings.pair_token_ttl_min)


@router.post("/sessions", status_code=201)
async def create_session(request: Request) -> dict:
    settings: Settings = request.app.state.settings
    owner_token, pair_token = new_token(), new_token()
    capture = CaptureSession(
        id=uuid4().hex,
        owner_token_hash=token_hash(owner_token),
        pair_token_hash=token_hash(pair_token),
        pair_expires_at=_new_pair_expiry(settings),
    )
    with request.app.state.database.session() as db:
        db.add(capture)
        db.commit()
        # The next stage can watch for manifest.json without special-casing "new".
        write_manifest(db, settings, capture.id)
    return {
        "session_id": capture.id,
        "owner_token": owner_token,
        "pair_token": pair_token,
        "pair_expires_at": iso(capture.pair_expires_at),
        "phone_url": settings.phone_url(pair_token),
    }


@router.post("/sessions/{session_id}/pair-token")
async def reissue_pair_token(
    session_id: str,
    request: Request,
    capture: CaptureSession = Depends(require_owner()),
) -> dict:
    """Rotates the pair token, which invalidates the QR code already on the wall."""
    settings: Settings = request.app.state.settings
    pair_token = new_token()
    with request.app.state.database.session() as db:
        stored = db.get(CaptureSession, session_id)
        stored.pair_token_hash = token_hash(pair_token)
        stored.pair_expires_at = _new_pair_expiry(settings)
        db.commit()
    return {
        "pair_token": pair_token,
        "pair_expires_at": iso(stored.pair_expires_at),
        "phone_url": settings.phone_url(pair_token),
    }


@router.get("/pair/{pair_token}")
async def check_pair_token(pair_token: str, request: Request) -> dict:
    """Upload-only lookup used by the phone page. Reveals nothing but the session id."""
    with request.app.state.database.session() as db:
        capture, reason = session_for_pair_token(db, pair_token)
        if capture is None:
            status = 410 if reason == PAIR_EXPIRED else 404
            raise HTTPException(status_code=status, detail=f"pair token {reason}")
        return {
            "session_id": capture.id,
            "expires_at": iso(capture.pair_expires_at),
        }


@router.get("/sessions/{session_id}/manifest")
async def get_manifest(
    session_id: str, request: Request, _: CaptureSession = Depends(require_owner())
) -> dict:
    with request.app.state.database.session() as db:
        return manifest_payload(db, session_id)


@router.get("/sessions/{session_id}/events")
async def stream_events(
    request: Request, capture: CaptureSession = Depends(require_owner(allow_query_token=True))
) -> EventSourceResponse:
    broker = request.app.state.broker
    # Subscribe before the snapshot: an event published during the DB read still
    # reaches the client (it may duplicate the snapshot, which is harmless).
    queue = broker.subscribe(capture.id)
    with request.app.state.database.session() as db:
        snapshot = manifest_payload(db, capture.id)

    async def publisher():
        try:
            yield {"event": SNAPSHOT, "data": json.dumps(snapshot)}
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                except TimeoutError:
                    yield {"comment": "keep-alive"}
                    continue
                yield {"event": message["event"], "data": json.dumps(message["data"])}
        finally:
            broker.unsubscribe(capture.id, queue)

    # ping=0 (not None, which means "use the default"): this generator sends its own.
    return EventSourceResponse(publisher(), ping=0)


async def _asset_file(request: Request, session_id: str, asset_id: str, attribute: str):
    settings: Settings = request.app.state.settings
    with request.app.state.database.session() as db:
        asset = db.get(Asset, asset_id)
        if asset is None or asset.session_id != session_id:
            raise HTTPException(status_code=404, detail="no such asset")
        relative = getattr(asset, attribute)
        media_type = (asset.mime or "application/octet-stream") if attribute == "stored_path" else "image/jpeg"
    if relative is None:
        raise HTTPException(status_code=404, detail="no such file")
    path = settings.data_dir / relative
    if not path.is_file():
        raise HTTPException(status_code=404, detail="file is gone from disk")
    # Starlette's FileResponse implements Range (206 + Content-Range) natively, which
    # is what lets videos seek.
    return FileResponse(path, media_type=media_type)


@router.get("/sessions/{session_id}/assets/{asset_id}/file")
async def get_asset_file(
    session_id: str,
    asset_id: str,
    request: Request,
    capture: CaptureSession = Depends(require_owner(allow_query_token=True)),
):
    return await _asset_file(request, session_id, asset_id, "stored_path")


@router.get("/sessions/{session_id}/assets/{asset_id}/thumb")
async def get_asset_thumb(
    session_id: str,
    asset_id: str,
    request: Request,
    capture: CaptureSession = Depends(require_owner(allow_query_token=True)),
):
    return await _asset_file(request, session_id, asset_id, "thumb_path")
