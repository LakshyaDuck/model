"""Serving stored files back to the laptop, including Range for video seeking."""

from __future__ import annotations

from .conftest import photo_meta, upload_through_hooks


def test_file_is_served_with_range_support(client, settings, new_session, owner_headers, image_bytes):
    session_id = new_session["session_id"]
    asset_id = upload_through_hooks(client, settings, photo_meta(new_session), image_bytes)
    base = f"/api/sessions/{session_id}/assets/{asset_id}/file"

    whole = client.get(base, headers=owner_headers)
    assert whole.status_code == 200
    assert whole.content == image_bytes
    assert whole.headers["content-type"] == "image/jpeg"
    assert whole.headers["accept-ranges"] == "bytes"

    part = client.get(base, headers={**owner_headers, "Range": "bytes=2-5"})
    assert part.status_code == 206
    assert part.content == image_bytes[2:6]
    assert part.headers["content-range"] == f"bytes 2-5/{len(image_bytes)}"


def test_thumbnail_is_served(client, settings, new_session, owner_headers, image_bytes):
    session_id = new_session["session_id"]
    asset_id = upload_through_hooks(client, settings, photo_meta(new_session), image_bytes)
    thumb = client.get(f"/api/sessions/{session_id}/assets/{asset_id}/thumb", headers=owner_headers)
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/jpeg"
    assert thumb.content.startswith(b"\xff\xd8")  # jpeg


def test_files_need_the_owner_token(client, settings, new_session, image_bytes):
    session_id = new_session["session_id"]
    asset_id = upload_through_hooks(client, settings, photo_meta(new_session), image_bytes)
    base = f"/api/sessions/{session_id}/assets/{asset_id}"
    assert client.get(f"{base}/file").status_code == 401
    assert client.get(f"{base}/file?token={new_session['pair_token']}").status_code == 401
    # a media tag cannot set headers
    assert client.get(f"{base}/thumb?token={new_session['owner_token']}").status_code == 200


def test_unknown_and_foreign_assets_are_404(client, settings, new_session, owner_headers, image_bytes):
    session_id = new_session["session_id"]
    asset_id = upload_through_hooks(client, settings, photo_meta(new_session), image_bytes)
    assert client.get(
        f"/api/sessions/{session_id}/assets/does-not-exist/file", headers=owner_headers
    ).status_code == 404

    other = client.post("/api/sessions").json()
    assert client.get(
        f"/api/sessions/{other['session_id']}/assets/{asset_id}/file",
        headers={"Authorization": f"Bearer {other['owner_token']}"},
    ).status_code == 404