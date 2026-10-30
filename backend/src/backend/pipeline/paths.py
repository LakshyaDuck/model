"""Session layout used by the Process job and its pipeline stages.

Keeping the directory names here means the job manager and every stage agree on
where files live. These helpers only build paths; they never create directories.
"""

from __future__ import annotations

from pathlib import Path

from ..config import Settings

PROCESSED_DIRNAME = "processed"
IMAGES_DIRNAME = "images"
INPUTS_NAME = "inputs.json"
EXTRACTED_FRAMES_DIRNAME = "extracted_frames"
RECONSTRUCTION_DIRNAME = "reconstruction"
COLMAP_DIRNAME = "colmap"
COLMAP_DATABASE_NAME = "database.db"
SPARSE_DIRNAME = "sparse"
DENSE_DIRNAME = "dense"
ARTIFACTS_DIRNAME = "artifacts"
ARTIFACTS_VERSION = "v1"


def processed_dir(settings: Settings, session_id: str) -> Path:
    return settings.session_dir(session_id) / PROCESSED_DIRNAME


def images_dir(settings: Settings, session_id: str) -> Path:
    return processed_dir(settings, session_id) / IMAGES_DIRNAME


def inputs_file(settings: Settings, session_id: str) -> Path:
    return processed_dir(settings, session_id) / INPUTS_NAME


def extracted_frames_dir(settings: Settings, session_id: str) -> Path:
    return settings.session_dir(session_id) / EXTRACTED_FRAMES_DIRNAME


def colmap_run_dir(settings: Settings, session_id: str, run_id: str) -> Path:
    return (
        settings.session_dir(session_id)
        / RECONSTRUCTION_DIRNAME
        / COLMAP_DIRNAME
        / run_id
    )


def artifacts_dir(settings: Settings, session_id: str) -> Path:
    return (
        settings.session_dir(session_id)
        / ARTIFACTS_DIRNAME
        / ARTIFACTS_VERSION
    )


def relative_to_data(settings: Settings, path: Path) -> str:
    """Paths are stored relative to DATA_DIR, like Asset.stored_path."""
    try:
        return path.relative_to(settings.data_dir).as_posix()
    except ValueError:
        return path.as_posix()
