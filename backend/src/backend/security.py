"""Two-token security model.

owner_token: full read access (manifest, events, files) for the laptop.
pair_token: upload-only credential for the phone, short lived.

Only SHA-256 hashes are stored, so a leaked database cannot be replayed.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from sqlmodel import Session, select

from .models import CaptureSession, utcnow

TOKEN_BYTES = 24

PAIR_INVALID = "invalid"
PAIR_EXPIRED = "expired"


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def secret_ok(candidate: str | None, expected: str) -> bool:
    if not candidate:
        return False
    return hmac.compare_digest(candidate, expected)


def session_for_owner(db: Session, session_id: str, token: str | None) -> CaptureSession | None:
    session = db.get(CaptureSession, session_id)
    if session is None or not token:
        return None
    if not hmac.compare_digest(session.owner_token_hash, token_hash(token)):
        return None
    return session


def session_for_pair_token(
    db: Session, token: str | None
) -> tuple[CaptureSession | None, str | None]:
    """Returns (session, reason). reason is PAIR_INVALID or PAIR_EXPIRED."""
    if not token:
        return None, PAIR_INVALID
    session = db.exec(
        select(CaptureSession).where(CaptureSession.pair_token_hash == token_hash(token))
    ).first()
    if session is None:
        return None, PAIR_INVALID
    if session.pair_expires_at <= utcnow():
        return None, PAIR_EXPIRED
    return session, None


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()