"""Token hashing, expiry, owner auth and pair-token rotation."""

from __future__ import annotations

import hashlib
from datetime import timedelta

from backend.models import CaptureSession, utcnow
from backend.security import new_token, token_hash

from .conftest import photo_meta, post_hook


def test_tokens_are_urlsafe_and_unique():
    tokens = {new_token() for _ in range(200)}
    assert len(tokens) == 200
    assert all(len(token) == 32 for token in tokens)  # 24 random bytes, base64url
    alphabet = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    assert all(set(token) <= alphabet for token in tokens)


def test_only_hashes_are_stored(client, new_session):
    assert token_hash(new_session["owner_token"]) == hashlib.sha256(
        new_session["owner_token"].encode()
    ).hexdigest()
    with client.app.state.database.session() as db:
        stored = db.get(CaptureSession, new_session["session_id"])
        assert stored.owner_token_hash == token_hash(new_session["owner_token"])
        assert stored.pair_token_hash == token_hash(new_session["pair_token"])

    raw_db = client.app.state.settings.db_path.read_bytes()
    assert new_session["owner_token"].encode() not in raw_db
    assert new_session["pair_token"].encode() not in raw_db


def test_owner_token_is_required(client, new_session, owner_headers):
    base = f"/api/sessions/{new_session['session_id']}/manifest"
    assert client.get(base).status_code == 401
    assert client.get(base, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get(base, headers={"Authorization": "Basic x"}).status_code == 401
    assert client.get(base, headers=owner_headers).status_code == 200


def test_query_token_is_not_accepted_on_the_manifest(client, new_session):
    """Only events, media, and model endpoints take ?token=; everything else needs a header."""
    assert client.get(
        f"/api/sessions/{new_session['session_id']}/manifest?token={new_session['owner_token']}"
    ).status_code == 401


def test_expired_pair_token_is_gone(client, settings, new_session):
    with client.app.state.database.session() as db:
        stored = db.get(CaptureSession, new_session["session_id"])
        stored.pair_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()

    assert client.get(f"/api/pair/{new_session['pair_token']}").status_code == 410
    rejected = post_hook(
        client,
        "pre-create",
        {"ID": None, "Size": 1, "Offset": 0, "MetaData": photo_meta(new_session)},
    )
    assert rejected["RejectUpload"] is True
    assert rejected["HTTPResponse"]["StatusCode"] == 403


def test_unknown_pair_token_is_404(client):
    assert client.get("/api/pair/not-a-token").status_code == 404


def test_reissuing_pair_token_invalidates_the_old_one(client, new_session, owner_headers):
    session_id = new_session["session_id"]
    assert client.post(f"/api/sessions/{session_id}/pair-token").status_code == 401

    rotated = client.post(f"/api/sessions/{session_id}/pair-token", headers=owner_headers)
    assert rotated.status_code == 200, rotated.text
    body = rotated.json()
    assert body["phone_url"] == f"https://example.org/m/{body['pair_token']}"

    assert client.get(f"/api/pair/{new_session['pair_token']}").status_code == 404
    assert client.get(f"/api/pair/{body['pair_token']}").status_code == 200


def test_pair_token_cannot_read_anything(client, new_session):
    """A pair token is upload-only: it must not work as an owner token."""
    session_id = new_session["session_id"]
    pair_token = new_session["pair_token"]
    assert client.get(
        f"/api/sessions/{session_id}/manifest", headers={"Authorization": f"Bearer {pair_token}"}
    ).status_code == 401
    assert client.get(f"/api/sessions/{session_id}/manifest?token={pair_token}").status_code == 401
    assert client.post(
        f"/api/sessions/{session_id}/pair-token", headers={"Authorization": f"Bearer {pair_token}"}
    ).status_code == 401