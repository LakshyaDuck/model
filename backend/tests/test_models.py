"""Serving processed GLB artifacts to the laptop viewer."""

from __future__ import annotations

import json

from backend.pipeline import (
    COLLISION_FILENAME,
    SCENE_FILENAME,
    artifacts_dir,
    inputs_file,
)

SCENE = b"glTF scene bytes"
COLLISION = b"glTF collision bytes"


def _write_glbs(settings, session_id: str) -> None:
    artifact = artifacts_dir(settings, session_id)
    artifact.mkdir(parents=True, exist_ok=True)
    (artifact / SCENE_FILENAME).write_bytes(SCENE)
    (artifact / COLLISION_FILENAME).write_bytes(COLLISION)


def test_models_are_served_with_binary_content(
    client, settings, new_session, owner_headers
):
    session_id = new_session["session_id"]
    _write_glbs(settings, session_id)

    scene = client.get(f"/api/sessions/{session_id}/model", headers=owner_headers)
    assert scene.status_code == 200
    assert scene.content == SCENE
    assert scene.headers["content-type"] == "model/gltf-binary"
    assert "scene.glb" in scene.headers["content-disposition"]

    collision = client.get(
        f"/api/sessions/{session_id}/model/collision?token={new_session['owner_token']}"
    )
    assert collision.status_code == 200
    assert collision.content == COLLISION
    assert collision.headers["content-type"] == "model/gltf-binary"
    assert "collision.glb" in collision.headers["content-disposition"]


def test_models_require_the_owner_token(client, settings, new_session, owner_headers):
    session_id = new_session["session_id"]
    _write_glbs(settings, session_id)
    base = f"/api/sessions/{session_id}/model"

    assert client.get(base).status_code == 401
    assert client.get(f"{base}?token={new_session['pair_token']}").status_code == 401
    assert client.get(base, headers={"Authorization": "Bearer wrong"}).status_code == 401

    other = client.post("/api/sessions").json()
    assert client.get(
        f"/api/sessions/{other['session_id']}/model",
        headers={"Authorization": f"Bearer {other['owner_token']}"},
    ).status_code == 404


def test_model_is_404_until_the_artifact_exists(client, new_session, owner_headers):
    base = f"/api/sessions/{new_session['session_id']}/model"
    assert client.get(base, headers=owner_headers).status_code == 404
    assert client.get(f"{base}?token={new_session['owner_token']}").status_code == 404
    assert client.get(f"{base}/collision", headers=owner_headers).status_code == 404


def test_completed_job_reports_model_paths(client, settings, new_session, owner_headers):
    session_id = new_session["session_id"]
    inputs = inputs_file(settings, session_id)
    inputs.parent.mkdir(parents=True, exist_ok=True)
    inputs.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "generated_at": "2026-01-01T00:00:00Z",
                "source_count": 1,
                "image_count": 1,
                "sources": [],
                "images": [],
            }
        ),
        encoding="utf-8",
    )
    _write_glbs(settings, session_id)

    status = client.get(
        f"/api/sessions/{session_id}/process", headers=owner_headers
    ).json()
    assert status["status"] == "done"
    assert status["model_path"] == f"sessions/{session_id}/artifacts/v1/scene.glb"
    assert (
        status["collision_model_path"]
        == f"sessions/{session_id}/artifacts/v1/collision.glb"
    )
