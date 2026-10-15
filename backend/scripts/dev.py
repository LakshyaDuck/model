#!/usr/bin/env python3
"""Local dev stack: the API (uvicorn --reload) and tusd, sharing one DATA_DIR and secret.

One command instead of two shells and three exported env vars:

    uv run python scripts/dev.py

Ctrl-C stops both. The API must come up first, because tusd exits if its hook endpoint
is unreachable at startup, so the script waits for /healthz before launching tusd.

Env overrides (all optional): PUBLIC_BASE_URL, DATA_DIR, HOOK_SECRET, MAX_UPLOAD_BYTES.
What to visit is printed on startup.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SECRET = "dev-secret-please-change"
DEFAULT_MAX_UPLOAD_BYTES = 5 * 1024**3
INSTALL_TUSD = """tusd not found on PATH. Install it once:
  mkdir -p ~/.local/bin
  curl -sL https://github.com/tus/tusd/releases/download/v2.10.1/tusd_linux_amd64.tar.gz \\
    | tar xz -C /tmp tusd_linux_amd64/tusd
  mv /tmp/tusd_linux_amd64/tusd ~/.local/bin/tusd
  tusd -version"""


def find_tusd() -> str:
    found = shutil.which("tusd")
    if found:
        return found
    fallback = Path.home() / ".local" / "bin" / "tusd"
    if fallback.exists():
        return str(fallback)
    sys.exit(INSTALL_TUSD)


def wait_for(url: str, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
    return False


def detect_lan_ip() -> str | None:
    """The address of the interface on the default route — what a phone on the same
    network (or on this machine's hotspot) can reach. None if it cannot be determined."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--tusd-port", type=int, default=1080)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--no-reload", action="store_true", help="disable uvicorn autoreload")
    args = parser.parse_args()

    data_dir = Path(os.environ.get("DATA_DIR") or BACKEND_DIR / "data").expanduser().resolve()
    tus_dir = data_dir / "tus"
    secret = os.environ.get("HOOK_SECRET") or DEFAULT_SECRET
    lan_ip = detect_lan_ip()
    fallback = f"http://{lan_ip}:{args.api_port}" if lan_ip else f"http://localhost:{args.api_port}"
    base_url = os.environ.get("PUBLIC_BASE_URL") or fallback
    max_bytes = os.environ.get("MAX_UPLOAD_BYTES") or str(DEFAULT_MAX_UPLOAD_BYTES)

    tusd = find_tusd()
    tus_dir.mkdir(parents=True, exist_ok=True)

    api_env = {
        **os.environ,
        "PUBLIC_BASE_URL": base_url,
        "DATA_DIR": str(data_dir),
        "HOOK_SECRET": secret,
        "MAX_UPLOAD_BYTES": max_bytes,
    }

    api_cmd = [
        sys.executable, "-m", "uvicorn", "backend.main:app",
        "--host", args.host, "--port", str(args.api_port),
    ]
    if not args.no_reload:
        api_cmd.append("--reload")
    tusd_cmd = [
        tusd,
        "-upload-dir", str(tus_dir),
        "-port", str(args.tusd_port),
        "-base-path", "/files/",
        "-max-size", max_bytes,
        # The Vite dev server proxies /files, so tusd must trust X-Forwarded-* to
        # mint upload URLs on the origin the phone sees (not 127.0.0.1:1080).
        "-behind-proxy",
        "-hooks-enabled-events", "pre-create,post-create,post-finish,post-terminate",
        "-hooks-http", f"http://127.0.0.1:{args.api_port}/internal/tusd-hook?secret={secret}",
        "-disable-download",
        "-disable-concatenation",
    ]

    procs: list[subprocess.Popen] = []

    def shutdown(*_: object) -> None:
        for proc in procs:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        deadline = time.time() + 5
        for proc in procs:
            while proc.poll() is None and time.time() < deadline:
                time.sleep(0.1)
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"  DATA_DIR  {data_dir}")
    print(f"  laptop    {base_url}/dev/laptop")
    if lan_ip:
        print(f"  phone     scan the QR at {base_url}/dev/laptop")
        print(f"            (PUBLIC_BASE_URL={base_url}; the QR points the phone here)")
    print(f"  tusd      http://127.0.0.1:{args.tusd_port}/files/")
    print("\nstarting API (waiting for /healthz)...", flush=True)

    procs.append(subprocess.Popen(api_cmd, cwd=BACKEND_DIR, env=api_env, start_new_session=True))
    if not wait_for(f"http://127.0.0.1:{args.api_port}/healthz"):
        print("API did not become healthy; see its output above.", file=sys.stderr)
        shutdown()

    print("API up. starting tusd...\n", flush=True)
    procs.append(subprocess.Popen(tusd_cmd, cwd=BACKEND_DIR, start_new_session=True))

    while True:
        for proc in procs:
            code = proc.poll()
            if code is not None:
                print(f"\nprocess exited (code {code}); shutting down.", file=sys.stderr)
                shutdown()
        time.sleep(0.5)


if __name__ == "__main__":
    raise SystemExit(main())
