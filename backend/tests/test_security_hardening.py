"""Credentials must never reach a log line; SQLite must accept a second writer."""

from __future__ import annotations

import logging

import pytest
from sqlalchemy import text

from backend.config import ConfigError, load_settings
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


def _env(secret: str) -> dict[str, str]:
    return {
        "PUBLIC_BASE_URL": "https://capture.example.org",
        "DATA_DIR": "/data",
        "HOOK_SECRET": secret,
    }


def test_hex_hook_secret_is_accepted():
    # openssl rand -hex 24: what we tell people to use.
    assert load_settings(_env("9f2c" * 12)).hook_secret == "9f2c" * 12


def test_base64_hook_secret_is_rejected_because_query_decoding_mangles_it():
    # Render's Blueprint generateValue mints a base64 value; "+" becomes " " in the
    # hook URL query string, so the hook would 401 on every call. Fail at startup.
    with pytest.raises(ConfigError, match="URL-safe"):
        load_settings(_env("dGhpcyArIGhhcyArIHBsdXM="))


def test_short_hook_secret_is_rejected():
    with pytest.raises(ConfigError, match="at least"):
        load_settings(_env("too-short"))
