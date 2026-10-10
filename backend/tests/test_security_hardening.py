"""Credentials must never reach a log line; SQLite must accept a second writer."""

from __future__ import annotations

import logging

from sqlalchemy import text

from backend.db import Database
from backend.logging_setup import RedactingFilter, install, redact


def test_redacts_every_place_a_secret_can_hide():
    line = (
        'POST /internal/tusd-hook?secret=abc123&x=1 '
        'GET /api/sessions/ab/events?token=def456 '
        'GET /api/pair/ghi789 GET /m/jkl012'
    )
    cleaned = redact(line)
    for leaked in ("abc123", "def456", "ghi789", "jkl012"):
        assert leaked not in cleaned
    assert cleaned.count("REDACTED") == 4
    # non-secret parts survive, and the untouched parameter is not clobbered
    assert "&x=1" in cleaned and "events" in cleaned


def test_filter_rewrites_access_log_records():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1234", "GET", "/m/pairtokenvalue", "1.1", 200),
        None,
    )
    RedactingFilter().filter(record)
    assert "pairtokenvalue" not in record.getMessage()
    assert "REDACTED" in record.getMessage()


def test_install_is_idempotent():
    install()
    install()
    filters = [f for f in logging.getLogger("uvicorn.access").filters if isinstance(f, RedactingFilter)]
    assert len(filters) == 1


def test_sqlite_uses_wal_and_waits_for_the_lock(tmp_path):
    database = Database(str(tmp_path / "app.db"))
    with database.engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert connection.execute(text("PRAGMA busy_timeout")).scalar() == 5000
