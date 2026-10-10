#!/usr/bin/env python3
"""Upload a file through the real stack, exactly like the phone would.

    uv run python scripts/simulate_upload.py session_photo.jpg --kind photo

Needs a running API and tusd. Without --pair-token it creates a session through the
API first, so no browser is required. If an upload dies half way, pass the printed
upload URL to --resume-url to continue from the offset tusd already has.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import sys
import urllib.error
import urllib.request
from pathlib import Path

TUS_VERSION = "1.0.0"
CHUNK_SIZE = 4 * 1024 * 1024


def tus_request(url: str, method: str, body=None, headers: dict | None = None) -> dict:
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("Tus-Resumable", TUS_VERSION)
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request) as response:
            return dict(response.headers)
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise SystemExit(f"tusd rejected {method} {url}: {error.code} {detail}") from error


def metadata_header(pairs: dict[str, str]) -> str:
    """tus Upload-Metadata: "key base64(value)" pairs joined by commas."""
    return ",".join(f"{key} {base64.b64encode(value.encode()).decode()}" for key, value in pairs.items())


def create_upload(tusd: str, path: Path, size: int, mime: str, kind: str, pair_token: str) -> str:
    request = urllib.request.Request(f"{tusd.rstrip('/')}/files/", data=b"", method="POST")
    request.add_header("Tus-Resumable", TUS_VERSION)
    request.add_header("Upload-Length", str(size))
    request.add_header(
        "Upload-Metadata",
        metadata_header(
            {
                "pair_token": pair_token,
                "kind": kind,
                "filename": path.name,
                "filetype": mime,
            }
        ),
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.headers["Location"]
    except urllib.error.HTTPError as error:
        # A rejection here came from our pre-create hook: tusd turns RejectUpload into
        # this status code plus the message body, which is the useful part to show.
        detail = error.read().decode(errors="replace")
        raise SystemExit(f"rejected before upload: {error.code} {detail}") from error


def upload(args: argparse.Namespace, pair_token: str) -> None:
    path = Path(args.file)
    size = path.stat().st_size
    mime = args.filetype or mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    if args.resume_url:
        upload_url = args.resume_url
    else:
        upload_url = create_upload(args.tusd, path, size, mime, args.kind, pair_token)
        print(f"created {upload_url}")

    offset = 0
    if args.resume_url:
        offset = int(tus_request(upload_url, "HEAD").get("Upload-Offset", 0))
        print(f"resuming at offset {offset}")

    with path.open("rb") as handle:
        handle.seek(offset)
        while offset < size:
            chunk = handle.read(min(CHUNK_SIZE, size - offset))
            headers = tus_request(
                upload_url,
                "PATCH",
                body=chunk,
                headers={
                    "Content-Type": "application/offset+octet-stream",
                    "Upload-Offset": str(offset),
                },
            )
            offset = int(headers.get("Upload-Offset", offset + len(chunk)))
            print(f"\r{offset}/{size} bytes", end="", flush=True)
    print(f"\nupload finished: {path.name} ({size} B, {mime})")


def new_pair_token(api: str) -> str:
    request = urllib.request.Request(f"{api.rstrip('/')}/api/sessions", data=b"", method="POST")
    request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request) as response:
        created = json.loads(response.read())
    print(
        f"new session {created['session_id']}, "
        f"pair token valid until {created['pair_expires_at']}"
    )
    return created["pair_token"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", help="file to upload")
    parser.add_argument("--kind", default="photo", choices=["video", "photo", "floorplan", "sensor"])
    parser.add_argument("--tusd", default="http://127.0.0.1:1080", help="tusd base URL")
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--pair-token", help="existing pair token; a session is created when omitted")
    parser.add_argument("--filetype", help="override the guessed mime type")
    parser.add_argument("--resume-url", help="upload URL from a previous run to resume")
    args = parser.parse_args()

    pair_token = args.pair_token or new_pair_token(args.api)
    upload(args, pair_token)
    return 0


if __name__ == "__main__":
    sys.exit(main())