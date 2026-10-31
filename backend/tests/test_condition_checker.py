"""Parsing checks for the pipeline condition checker."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "condition_checker.py"
_SPEC = importlib.util.spec_from_file_location("condition_checker", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
checker = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = checker
_SPEC.loader.exec_module(checker)


def _line(status: str, stage: str, **fields: str) -> str:
    extra = " ".join(f"{key}={value}" for key, value in fields.items())
    return (
        f"2026-10-31 12:00:00,000 INFO backend.pipeline.run "
        f"pipeline stage={stage} status={status} {extra}"
    )


def test_parse_stage_extracts_fields_and_error_text():
    event = checker.parse_stage(
        _line(
            "failed",
            "features",
            session="demo",
            elapsed_ms="1234",
            run_id="r1",
            error="could not read image folder",
        )
    )
    assert event is not None
    assert event.stage == "features"
    assert event.status == "failed"
    assert event.session == "demo"
    assert event.elapsed_ms == "1234"
    assert event.error == "could not read image folder"


def test_parse_stage_ignores_unrelated_logs():
    assert checker.parse_stage("INFO:     127.0.0.1 - GET /healthz") is None


def test_tracker_filters_by_session_and_flags_missing_export(capsys):
    tracker = checker.StageTracker("demo")
    for line in (
        _line("start", "pipeline", session="other"),
        _line("start", "pipeline", session="demo"),
        _line(
            "skipped",
            "frames",
            session="demo",
            reason="no_frames_extracted",
        ),
        _line("ok", "pipeline", session="demo", elapsed_ms="0"),
    ):
        event = checker.parse_stage(line)
        assert event is not None
        tracker.feed(event)

    assert tracker.finish() == 0
    captured = capsys.readouterr()
    assert "session=demo" not in captured.out
    assert "without an export stage" in captured.err


def test_tracker_returns_failure_for_a_failed_stage(capsys):
    tracker = checker.StageTracker("demo")
    for line in (
        _line("start", "pipeline", session="demo"),
        _line("start", "mesh", session="demo", model="0"),
        _line(
            "failed",
            "mesh",
            session="demo",
            elapsed_ms="12",
            model="0",
            error="could not write mesh",
        ),
    ):
        event = checker.parse_stage(line)
        assert event is not None
        tracker.feed(event)

    assert tracker.finish() == 1
    captured = capsys.readouterr()
    assert "first failure: stage=mesh" in captured.err
