"""The tusd hook endpoint: validation, storage, and the states an asset moves through."""

from __future__ import annotations

import hashlib

from backend.models import READY, UPLOADING, Asset

from .conftest import (
    HOOK_SECRET,
    hook_payload,
    photo_meta,
    post_hook,
    upload_through_hooks,
    video_bytes,
)


def rejected_body(body: dict) -> dict:
    assert body.get("RejectUpload") is True, body
    return body["HTTPResponse"]


def test_hook_endpoint_requires_the_shared_secret(client, settings, new_session):
    payload = hook_payload(
        "pre-create",
        {"ID": None, "Size": 10, "Offset": 0, "MetaData": photo_meta(new_session)},
    )
    assert client.post("/internal/tusd-hook", json=payload).status_code == 401
    assert client.post(
        "/internal/tusd-hook", json=payload, headers={"X-Hook-Secret": "wrong"}
    ).status_code == 401
    # tusd cannot send headers of its own, so the secret may ride in the hook URL.
    assert client.post("/internal/tusd-hook", json=payload, params={"secret": HOOK_SECRET}).status_code == 200
    assert client.post(
        "/internal/tusd-hook", json=payload, params={"secret": "nope"}
    ).status_code == 401


def test_pre_create_rejects_bad_input(client, new_session):
    good = photo_meta(new_session)
    cases = {
        "missing metadata": {"kind": "photo"},
        "bad token": {**good, "pair_token": "not-a-real-token"},
        "bad kind": {**good, "kind": "screenshot"},
        "too large": good,
    }
    sizes = {"too large": 5 * 1024 * 1024}
    for label, meta in cases.items():
        body = post_hook(
            client, "pre-create", {"ID": None, "Size": sizes.get(label, 10), "MetaData": meta}
        )
        rejected = rejected_body(body)
        assert rejected["StatusCode"] in (400, 403, 413), label


def test_pre_create_enforces_the_asset_count_limit(client, settings, new_session, image_bytes):
    for index in range(settings.max_assets_per_session):
        upload_through_hooks(
            client, settings, photo_meta(new_session, f"p{index}.jpg"), image_bytes, tus_id=f"u{index}"
        )
    body = post_hook(
        client, "pre-create", {"ID": None, "Size": 10, "MetaData": photo_meta(new_session, "over.jpg")}
    )
    assert rejected_body(body)["StatusCode"] == 409


def test_pre_create_hands_session_and_asset_id_to_later_hooks(client, new_session):
    body = post_hook(
        client,
        "pre-create",
        {"ID": None, "Size": 10, "MetaData": photo_meta(new_session)},
    )
    meta = body["ChangeFileInfo"]["MetaData"]
    assert meta["session_id"] == new_session["session_id"]
    assert len(meta["asset_id"]) == 32
    # tusd replaces the metadata wholesale, so the phone's keys must survive.
    assert meta["pair_token"] == new_session["pair_token"]
    assert meta["filename"] == "photo.jpg" and meta["filetype"] == "image/jpeg"


def test_post_create_records_an_uploading_asset(client, settings, new_session):
    meta = post_hook(
        client, "pre-create", {"ID": None, "Size": 4, "MetaData": photo_meta(new_session)}
    )["ChangeFileInfo"]["MetaData"]
    post_hook(client, "post-create", {"ID": "abc123", "Size": 4, "MetaData": meta})
    with client.app.state.database.session() as db:
        asset = db.get(Asset, meta["asset_id"])
        assert (asset.status, asset.tus_upload_id, asset.kind) == (UPLOADING, "abc123", "photo")


def test_post_finish_stores_hashes_and_thumbnails(client, settings, new_session, image_bytes):
    asset_id = upload_through_hooks(client, settings, photo_meta(new_session), image_bytes)

    with client.app.state.database.session() as db:
        asset = db.get(Asset, asset_id)
        assert asset.status == READY
        assert asset.sha256 == hashlib.sha256(image_bytes).hexdigest()
        assert asset.size_bytes == len(image_bytes)
        # mime is recorded exactly as received, never normalized
        assert asset.mime == "image/jpeg"
        stored = settings.data_dir / asset.stored_path
        assert stored.read_bytes() == image_bytes
        assert stored.name == f"{asset_id}.jpg"
        assert (settings.data_dir / asset.thumb_path).is_file()
    assert not (settings.tus_dir / ("u" * 32)).exists()  # moved out of tus storage


def test_post_finish_keeps_odd_formats_untouched(client, settings, new_session):
    """HEVC .mov and the like are stored byte for byte; no transcoding happens."""
    body = video_bytes()
    meta = {**photo_meta(new_session), "kind": "video", "filename": "IMG_0001.MOV", "filetype": "video/quicktime"}
    asset_id = upload_through_hooks(client, settings, meta, body)
    with client.app.state.database.session() as db:
        asset = db.get(Asset, asset_id)
        assert asset.mime == "video/quicktime"
        assert asset.stored_path.endswith(".mov")
        assert (settings.data_dir / asset.stored_path).read_bytes() == body
        assert (settings.data_dir / asset.thumb_path).is_file()  # ffmpeg first frame


def test_post_finish_is_idempotent(client, settings, new_session, image_bytes):
    """tusd retries hooks, so a repeat must not corrupt the stored asset."""
    asset_id = upload_through_hooks(client, settings, photo_meta(new_session), image_bytes)
    meta = photo_meta(new_session)
    pre = post_hook(client, "pre-create", {"ID": None, "Size": len(image_bytes), "MetaData": meta})
    stored_meta = pre["ChangeFileInfo"]["MetaData"]
    post_hook(
        client,
        "post-finish",
        {
            "ID": "u" * 32,
            "Size": len(image_bytes),
            "Offset": len(image_bytes),
            "MetaData": stored_meta,
            "Storage": {"Type": "filestore", "Path": str(settings.tus_dir / ("u" * 32))},
        },
    )
    with client.app.state.database.session() as db:
        asset = db.get(Asset, asset_id)
        assert asset.status == READY
        assert (settings.data_dir / asset.stored_path).read_bytes() == image_bytes


def test_post_finish_marks_failed_when_the_data_vanished(client, settings, new_session):
    meta = photo_meta(new_session)
    pre = post_hook(client, "pre-create", {"ID": None, "Size": 4, "MetaData": meta})
    stored_meta = pre["ChangeFileInfo"]["MetaData"]
    post_hook(client, "post-create", {"ID": "gone", "Size": 4, "MetaData": stored_meta})
    post_hook(
        client,
        "post-finish",
        {
            "ID": "gone",
            "Size": 4,
            "Offset": 4,
            "MetaData": stored_meta,
            "Storage": {"Type": "filestore", "Path": str(settings.tus_dir / "never-existed")},
        },
    )
    with client.app.state.database.session() as db:
        asset = db.get(Asset, stored_meta["asset_id"])
        assert asset.status == "failed"
        assert "FileNotFoundError" in asset.error_reason


def test_post_finish_before_post_create_still_works(client, settings, new_session, image_bytes):
    """tusd makes no ordering guarantee between post-create and post-finish."""
    meta = photo_meta(new_session)
    pre = post_hook(client, "pre-create", {"ID": None, "Size": len(image_bytes), "MetaData": meta})
    stored_meta = pre["ChangeFileInfo"]["MetaData"]
    source = settings.tus_dir / "ooo"
    source.write_bytes(image_bytes)
    post_hook(
        client,
        "post-finish",
        {
            "ID": "ooo",
            "Size": len(image_bytes),
            "Offset": len(image_bytes),
            "MetaData": stored_meta,
            "Storage": {"Type": "filestore", "Path": str(source)},
        },
    )
    post_hook(client, "post-create", {"ID": "ooo", "Size": len(image_bytes), "MetaData": stored_meta})
    with client.app.state.database.session() as db:
        assert db.get(Asset, stored_meta["asset_id"]).status == READY


def test_post_terminate_removes_the_asset(client, settings, new_session, image_bytes):
    asset_id = upload_through_hooks(client, settings, photo_meta(new_session), image_bytes)
    with client.app.state.database.session() as db:
        stored_path = db.get(Asset, asset_id).stored_path

    post_hook(client, "post-terminate", {"ID": "u" * 32, "MetaData": {}})

    with client.app.state.database.session() as db:
        assert db.get(Asset, asset_id) is None
    assert not (settings.data_dir / stored_path).exists()
    manifest = (settings.session_dir(new_session["session_id"]) / "manifest.json").read_text()
    assert asset_id not in manifest


def test_unknown_hook_type_is_ignored(client):
    assert post_hook(client, "post-receive", {"ID": "x", "Offset": 5}) == {}


def test_hooks_without_pre_create_metadata_are_skipped(client):
    assert post_hook(client, "post-create", {"ID": "x", "MetaData": {"kind": "video"}}) == {}