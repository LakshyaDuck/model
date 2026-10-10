"""manifest.json is the hand-off to the next pipeline stage, so it must be exact."""

from __future__ import annotations

import json

import pytest
from backend.config import Settings
from backend.manifest import write_manifest
from backend.models import CaptureSession, utcnow

from .conftest import photo_meta, post_hook, read_manifest, upload_through_hooks


def seed(client, settings: Settings, session_id: str) -> None:
    with client.app.state.database.session() as db:
        db.add(
            CaptureSession(
                id=session_id,
                owner_token_hash="x",
                pair_token_hash="y",
                pair_expires_at=utcnow(),
            )
        )
        db.commit()


def test_manifest_lists_every_asset_field(client, settings, new_session, image_bytes):
    session_id = new_session["session_id"]
    asset_id = upload_through_hooks(client, settings, photo_meta(new_session), image_bytes)

    manifest = read_manifest(settings, session_id)
    assert manifest["session_id"] == session_id
    assert manifest["asset_count"] == 1
    asset = manifest["assets"][0]
    assert asset == {
        "id": asset_id,
        "session_id": session_id,
        "kind": "photo",
        "original_filename": "photo.jpg",
        "mime": "image/jpeg",
        "size_bytes": len(image_bytes),
        "sha256": asset["sha256"],
        "status": "ready",
        "stored_path": asset["stored_path"],
        "thumb_path": asset["thumb_path"],
        "error_reason": None,
        "created_at": asset["created_at"],
    }
    # paths are relative to DATA_DIR so the tree stays relocatable
    assert asset["stored_path"] == f"sessions/{session_id}/raw/{asset_id}.jpg"


def test_manifest_is_written_on_every_asset_change(client, settings, new_session, image_bytes):
    session_id = new_session["session_id"]
    body = image_bytes
    meta = photo_meta(new_session)

    pre = post_hook(client, "pre-create", {"ID": None, "Size": len(body), "MetaData": meta})
    assert read_manifest(settings, session_id)["asset_count"] == 0  # nothing created yet
    stored_meta = pre["ChangeFileInfo"]["MetaData"]

    post_hook(client, "post-create", {"ID": "u" * 32, "Size": len(body), "MetaData": stored_meta})
    assert [a["status"] for a in read_manifest(settings, session_id)["assets"]] == ["uploading"]

    source = settings.tus_dir / ("u" * 32)
    source.write_bytes(body)
    post_hook(
        client,
        "post-finish",
        {
            "ID": "u" * 32,
            "Size": len(body),
            "Offset": len(body),
            "MetaData": stored_meta,
            "Storage": {"Type": "filestore", "Path": str(source)},
        },
    )
    assert read_manifest(settings, session_id)["assets"][0]["status"] == "ready"

    post_hook(client, "post-terminate", {"ID": "u" * 32, "MetaData": {}})
    assert read_manifest(settings, session_id)["asset_count"] == 0


def test_manifest_write_is_atomic(client, settings, tmp_path):
    """A crash while writing must leave the previous manifest in place."""
    session_id = "atomic"
    seed(client, settings, session_id)
    with client.app.state.database.session() as db:
        first = write_manifest(db, settings, session_id)

    real_write_text = type(first).write_text

    def exploding_write_text(self, text, **kwargs):
        real_write_text(self, text[:20], **kwargs)  # partial temp file, then boom
        raise OSError("disk full")

    with pytest.raises(OSError):
        with client.app.state.database.session() as db:
            type(first).write_text = exploding_write_text
            try:
                write_manifest(db, settings, session_id)
            finally:
                type(first).write_text = real_write_text

    assert json.loads(first.read_text())["session_id"] == session_id
    # a successful rewrite cleans up after itself
    with client.app.state.database.session() as db:
        write_manifest(db, settings, session_id)
    assert list(first.parent.glob("*.tmp")) == []


def test_manifest_dir_is_created_for_a_new_session(client, settings, tmp_path):
    session_id = "fresh"
    seed(client, settings, session_id)
    with client.app.state.database.session() as db:
        path = write_manifest(db, settings, session_id)
    assert path == settings.session_dir(session_id) / "manifest.json"
    assert path.is_file()


def test_manifest_endpoint_matches_the_file(client, settings, new_session, image_bytes):
    upload_through_hooks(client, settings, photo_meta(new_session), image_bytes)
    session_id = new_session["session_id"]

    from_disk = read_manifest(settings, session_id)
    from_api = client.get(
        f"/api/sessions/{session_id}/manifest",
        headers={"Authorization": f"Bearer {new_session['owner_token']}"},
    ).json()
    assert from_disk["assets"] == from_api["assets"]
