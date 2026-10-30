"""COLMAP feature matching for a database built by ``feature_extraction``.

``match_features`` is importable and has no import-time side effects. It runs
exhaustive matching over the SIFT features already stored in the COLMAP database.
``run.pipeline`` calls it after ``extract_features``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pycolmap

logger = logging.getLogger(__name__)


def match_features(database_path: str | Path) -> Path:
    """Exhaustively match features in the COLMAP database.

    Returns ``database_path``. Raises ``FileNotFoundError`` when the database is
    missing (run feature extraction first).
    """
    database = Path(database_path)
    if not database.is_file():
        raise FileNotFoundError(
            f"COLMAP database not found: {database}; run feature extraction first"
        )

    logger.info("matching features in %s", database)
    pycolmap.match_exhaustive(database_path=str(database))
    logger.info("feature matching finished for %s", database)
    return database
