"""manifest.json is a derived export for the next pipeline stage.

Rewrite it (temp file + rename) after every asset change so a reader never sees a
half-written file and never has to talk to SQLite.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from sqlmodel import Session, select

from .config import Settings
from .models import Asset, asset_json, iso, utcnow

MANIFEST_NAME = "manifest.json"


def manifest_file(settings: Settings, session_id: str) -> Path:
    return settings.session_dir(session_id) / MANIFEST_NAME


def manifest_payload(db: Session, session_id: str) -> dict:
    assets = db.exec(
        select(Asset).where(Asset.session_id == session_id).order_by(Asset.created_at)
    ).all()
    return {
        "session_id": session_id,
        "generated_at": iso(utcnow()),
        "asset_count": len(assets),
        "assets": [asset_json(asset) for asset in assets],
    }


def write_manifest(db: Session, settings: Settings, session_id: str) -> Path:
    target = manifest_file(settings, session_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(manifest_payload(db, session_id), indent=2) + "\n"
    tmp = target.with_name(f"{target.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)  # same directory, so this is atomic
    return target