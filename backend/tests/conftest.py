"""Shared fixtures: every test gets its own DATA_DIR, database and app."""

from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import time
from io import BytesIO
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
import uvicorn
from fastapi.testclient import TestClient
from PIL import Image

from backend.config import Settings
from backend.main import create_app

HOOK_SECRET = "test-hook-secret-0123456789"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        public_base_url="https://example.org",
        data_dir=tmp_path / "data",
        pair_token_ttl_min=30,
        max_upload_bytes=1024 * 1024,
        max_assets_per_session=3,
        hook_secret=HOOK_SECRET,
        cors_origins=["https://example.org"],
    )


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest_asyncio.fixture
async def live_server(app) -> str:
    """A real uvicorn server on an ephemeral port.

    TestClient and httpx's ASGITransport both buffer the whole response body before
    returning, which never completes for an endless SSE stream.
    """
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started, "uvicorn did not start"
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture
def new_session(client) -> dict:
    response = client.post("/api/sessions")
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def owner_headers(new_session) -> dict:
    return {"Authorization": f"Bearer {new_session['owner_token']}"}


@pytest.fixture
def image_bytes() -> bytes:
    """Smallest thing Pillow is happy with."""
    buffer = BytesIO()
    Image.new("RGB", (8, 6), (200, 30, 30)).save(buffer, format="JPEG")
    return buffer.getvalue()


def video_bytes() -> bytes:
    """A tiny real mp4, so the ffmpeg thumbnail path actually runs."""
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "clip.mp4"
        subprocess.run(
            [
                "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc=duration=0.5:size=64x48:rate=5",
                "-pix_fmt", "yuv420p", str(target),
            ],
            check=True,
        )
        return target.read_bytes()


def hook_payload(hook_type: str, upload: dict) -> dict:
    return {
        "Type": hook_type,
        "Event": {
            "Upload": upload,
            "HTTPRequest": {
                "Method": "POST",
                "URI": "/files/",
                "RemoteAddr": "127.0.0.1:5000",
                "Header": {"Tus-Resumable": ["1.0.0"]},
            },
        },
    }


def post_hook(client, hook_type: str, upload: dict, secret: str = HOOK_SECRET) -> dict:
    response = client.post(
        "/internal/tusd-hook",
        json=hook_payload(hook_type, upload),
        headers={"X-Hook-Secret": secret},
    )
    assert response.status_code == 200, response.text
    return response.json()


def photo_meta(new_session: dict, filename: str = "photo.jpg", mime: str = "image/jpeg") -> dict:
    return {
        "pair_token": new_session["pair_token"],
        "kind": "photo",
        "filename": filename,
        "filetype": mime,
    }


def upload_through_hooks(
    client, settings: Settings, meta: dict, body: bytes, tus_id: str = "u" * 32
) -> str:
    """Drive pre-create -> post-create -> post-finish and return the asset id."""
    pre = post_hook(
        client,
        "pre-create",
        {"ID": None, "Size": len(body), "SizeIsDeferred": False, "Offset": 0, "MetaData": meta},
    )
    assert "ChangeFileInfo" in pre, pre
    meta = pre["ChangeFileInfo"]["MetaData"]
    post_hook(client, "post-create", {"ID": tus_id, "Size": len(body), "Offset": 0, "MetaData": meta})

    source = settings.tus_dir / tus_id
    source.write_bytes(body)
    post_hook(
        client,
        "post-finish",
        {
            "ID": tus_id,
            "Size": len(body),
            "Offset": len(body),
            "MetaData": meta,
            "Storage": {"Type": "filestore", "Path": str(source), "InfoPath": f"{source}.info"},
        },
    )
    return meta["asset_id"]


def read_manifest(settings: Settings, session_id: str) -> dict:
    return json.loads((settings.session_dir(session_id) / "manifest.json").read_text())


def next_event(lines) -> tuple[str, str]:
    """Read one SSE frame off an httpx line iterator, skipping comments."""
    name, data = None, []
    for line in lines:
        if line.startswith("event:"):
            name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data.append(line[len("data:") :].strip())
        elif not line.strip() and name:
            return name, "\n".join(data)
    raise AssertionError("event stream ended early")