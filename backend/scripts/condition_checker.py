#!/usr/bin/env python3
"""Tail pipeline logs and show every reconstruction stage.

``backend.pipeline.run`` emits one line per stage transition::

    pipeline stage=mesh status=start session=<id> model=0
    pipeline stage=mesh status=ok session=<id> elapsed_ms=1234 model=0
    pipeline stage=mesh status=failed session=<id> elapsed_ms=12 model=0 error=...
    pipeline stage=dense status=skipped session=<id> reason=no_backend model=0

Read those lines from stdin, a log file, or ``docker compose logs`` and print a
compact timeline. Exits non-zero if a stage failed or started but never finished.

Examples::

    docker compose logs -f api | python3 backend/scripts/condition_checker.py --session <id>
    python3 backend/scripts/condition_checker.py --compose --session <id>
    python3 backend/scripts/condition_checker.py --file api.log
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_STAGE_RE = re.compile(r"\bstage=(\S+)\s+status=(\S+)")
_KEY_RE = re.compile(r"(?:^|\s)([A-Za-z_]\w*)=")
_TIME_RE = re.compile(r"\b(\d{2}:\d{2}:\d{2})\b")
_HIDDEN_FIELDS = {"stage", "status", "session", "elapsed_ms"}


@dataclass(frozen=True)
class StageEvent:
    stage: str
    status: str
    session: str | None
    fields: dict[str, str]
    raw: str

    @property
    def elapsed_ms(self) -> str | None:
        return self.fields.get("elapsed_ms")

    @property
    def error(self) -> str:
        return self.fields.get("error", "")

    @property
    def reason(self) -> str:
        return self.fields.get("reason", "")

    def details(self, *, hide: set[str] | None = None) -> str:
        hidden = _HIDDEN_FIELDS | (hide or set())
        return " ".join(
            f"{key}={value}"
            for key, value in self.fields.items()
            if key not in hidden
        )


def _field(line: str, name: str) -> str | None:
    pattern = rf"(?:^|\s){re.escape(name)}=(.*?)(?=\s+[A-Za-z_]\w*=|$)"
    match = re.search(pattern, line)
    return match.group(1) if match else None


def parse_stage(line: str) -> StageEvent | None:
    """Return a StageEvent for a pipeline log line, or None for other logs."""
    clean = _ANSI_RE.sub("", line).rstrip("\r\n")
    match = _STAGE_RE.search(clean)
    if match is None:
        return None
    stage, status = match.groups()
    fields: dict[str, str] = {}
    for key_match in _KEY_RE.finditer(clean):
        key = key_match.group(1)
        value = _field(clean, key)
        if value is not None:
            fields[key] = value
    return StageEvent(
        stage=stage,
        status=status,
        session=fields.get("session"),
        fields=fields,
        raw=clean,
    )


def _timestamp(raw: str) -> str:
    match = _TIME_RE.search(raw)
    return match.group(1) if match else time.strftime("%H:%M:%S")


def _suffix(event: StageEvent, *, hide: set[str] | None = None) -> str:
    details = event.details(hide=hide)
    return f" {details}" if details else ""


class StageTracker:
    """Render stage events and keep enough state to flag incomplete runs."""

    def __init__(self, session: str | None = None) -> None:
        self.session = session
        self.events: list[StageEvent] = []
        self.open: list[StageEvent] = []
        self.failures: list[StageEvent] = []
        self.skips: list[StageEvent] = []
        self.ok_count = 0

    def feed(self, event: StageEvent) -> None:
        if self.session is not None and event.session != self.session:
            return
        self.events.append(event)
        stamp = _timestamp(event.raw)

        if event.status == "start":
            self.open.append(event)
            print(f"[{stamp}] START   {event.stage}{_suffix(event)}", flush=True)
            return

        self._close(event.stage)

        if event.status == "ok":
            self.ok_count += 1
            elapsed = event.elapsed_ms
            timing = f" ({elapsed}ms)" if elapsed else ""
            print(
                f"[{stamp}] OK      {event.stage}{_suffix(event)}{timing}",
                flush=True,
            )
        elif event.status == "failed":
            self.failures.append(event)
            print(
                f"[{stamp}] FAILED  {event.stage}"
                f"{_suffix(event, hide={'error'})} error={event.error}",
                flush=True,
            )
        elif event.status == "skipped":
            self.skips.append(event)
            print(
                f"[{stamp}] SKIP    {event.stage}"
                f"{_suffix(event, hide={'reason'})} reason={event.reason}",
                flush=True,
            )
        else:
            print(
                f"[{stamp}] {event.status.upper():7} {event.stage}{_suffix(event)}",
                flush=True,
            )

    def _close(self, stage: str) -> None:
        for index in range(len(self.open) - 1, -1, -1):
            if self.open[index].stage == stage:
                del self.open[index]
                return

    def finish(self) -> int:
        print(flush=True)
        for event in self.open:
            print(
                f"WARNING: stage={event.stage} started but never reached ok/failed"
                f"{_suffix(event)}",
                file=sys.stderr,
                flush=True,
            )

        if not self.events:
            print("No pipeline stage lines seen.", file=sys.stderr, flush=True)
            return 2

        exported = any(
            event.stage == "export" and event.status == "ok" for event in self.events
        )
        finished = any(
            event.stage == "pipeline" and event.status == "ok"
            for event in self.events
        )
        if finished and not exported and not self.failures:
            print(
                "WARNING: pipeline finished without an export stage; no GLB was produced",
                file=sys.stderr,
                flush=True,
            )

        print(
            f"summary: {self.ok_count} ok, {len(self.skips)} skipped, "
            f"{len(self.failures)} failed, {len(self.open)} unfinished",
            flush=True,
        )
        if self.failures:
            first = self.failures[0]
            print(
                f"first failure: stage={first.stage}"
                f"{_suffix(first, hide={'error'})} error={first.error}",
                file=sys.stderr,
                flush=True,
            )
        return 1 if self.failures or self.open else 0


def _stdin_lines() -> Iterator[str]:
    yield from sys.stdin


def _file_lines(path: Path, follow: bool) -> Iterator[str]:
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        if follow:
            stream.seek(0, os.SEEK_END)
        while True:
            line = stream.readline()
            if line:
                yield line
            elif follow:
                time.sleep(0.2)
            else:
                return


def _compose_lines(service: str) -> Iterator[str]:
    if shutil.which("docker") is None:
        raise FileNotFoundError("docker is not on PATH")
    repo_root = Path(__file__).resolve().parents[2]
    process = subprocess.Popen(
        ["docker", "compose", "logs", "--follow", service],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        assert process.stdout is not None
        yield from process.stdout
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def _iter_source(args: argparse.Namespace) -> Iterator[str]:
    if args.compose:
        yield from _compose_lines(args.compose)
    elif args.file:
        yield from _file_lines(Path(args.file), args.follow)
    else:
        yield from _stdin_lines()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--session",
        help="only show lines for this session id",
    )
    parser.add_argument(
        "--compose",
        nargs="?",
        const="api",
        metavar="SERVICE",
        help="run `docker compose logs -f SERVICE` (default: api)",
    )
    parser.add_argument(
        "--file",
        help="read a log file instead of stdin",
    )
    parser.add_argument(
        "--follow",
        action="store_true",
        help="keep reading --file after EOF",
    )
    args = parser.parse_args(argv)

    if not args.compose and not args.file and sys.stdin.isatty():
        parser.error("pipe logs on stdin, or use --compose / --file")

    tracker = StageTracker(args.session)
    source = _iter_source(args)
    try:
        for line in source:
            event = parse_stage(line)
            if event is not None:
                tracker.feed(event)
    except KeyboardInterrupt:
        print()
    except (OSError, FileNotFoundError) as exc:
        print(f"condition_checker: {exc}", file=sys.stderr)
        return 2
    finally:
        source.close()
    return tracker.finish()


if __name__ == "__main__":
    raise SystemExit(main())
