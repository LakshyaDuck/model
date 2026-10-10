"""SQLModel tables. SQLite is the source of truth; manifest.json is derived."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel

VIDEO = "video"
PHOTO = "photo"
FLOORPLAN = "floorplan"
SENSOR = "sensor"
KINDS = frozenset({VIDEO, PHOTO, FLOORPLAN, SENSOR})

UPLOADING = "uploading"
STORED = "stored"
READY = "ready"
FAILED = "failed"
STATUSES = frozenset({UPLOADING, STORED, READY, FAILED})

# Timestamps are aware UTC. SQLite has no timezone type, so SQLModel's UTCDateTime
# reattaches UTC on read; do not mix naive values in.
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.isoformat(timespec="seconds") + "Z"


class CaptureSession(SQLModel, table=True):
    __tablename__ = "sessions"

    id: str = Field(primary_key=True)
    owner_token_hash: str
    pair_token_hash: str
    pair_expires_at: datetime
    created_at: datetime = Field(default_factory=utcnow)


class Asset(SQLModel, table=True):
    __tablename__ = "assets"

    id: str = Field(primary_key=True)
    session_id: str = Field(index=True, foreign_key="sessions.id")
    kind: str
    original_filename: str = ""
    mime: str = ""
    size_bytes: int = 0
    sha256: str | None = None
    status: str = UPLOADING
    # Paths are relative to DATA_DIR so the tree can be relocated wholesale.
    stored_path: str | None = None
    thumb_path: str | None = None
    # tusd's upload ID, learned in post-create/post-finish; the only handle we have
    # on a DELETE (post-terminate) hook.
    tus_upload_id: str | None = Field(default=None, index=True)
    error_reason: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


def asset_json(asset: Asset) -> dict:
    """Single serialization used by the manifest and by every SSE event."""
    return {
        "id": asset.id,
        "session_id": asset.session_id,
        "kind": asset.kind,
        "original_filename": asset.original_filename,
        "mime": asset.mime,
        "size_bytes": asset.size_bytes,
        "sha256": asset.sha256,
        "status": asset.status,
        "stored_path": asset.stored_path,
        "thumb_path": asset.thumb_path,
        "error_reason": asset.error_reason,
        "created_at": iso(asset.created_at),
    }