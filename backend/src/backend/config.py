"""Settings come from the environment only and are validated once at startup."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_PAIR_TOKEN_TTL_MIN = 30
DEFAULT_MAX_UPLOAD_BYTES = 5 * 1024**3  # 5 GB
DEFAULT_MAX_ASSETS_PER_SESSION = 200
MIN_HOOK_SECRET_LEN = 16

# The secret is embedded in the tusd hook URL, so it must survive a URL query
# round-trip. A base64 secret with "+" arrives here url-decoded as a space and every
# hook 401s, so only RFC 3986 unreserved characters are accepted.
_URL_SAFE_SECRET = re.compile(r"^[A-Za-z0-9._~-]+$")


class ConfigError(RuntimeError):
    """Environment is missing or unusable; fatal at startup."""


@dataclass(frozen=True)
class Settings:
    public_base_url: str
    data_dir: Path
    pair_token_ttl_min: int = DEFAULT_PAIR_TOKEN_TTL_MIN
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    max_assets_per_session: int = DEFAULT_MAX_ASSETS_PER_SESSION
    hook_secret: str = ""
    cors_origins: list[str] = field(default_factory=list)

    @property
    def tus_dir(self) -> Path:
        """Shared with the tusd container; moves out of here must stay on one volume."""
        return self.data_dir / "tus"

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    def session_dir(self, session_id: str) -> Path:
        return self.sessions_dir / session_id

    def phone_url(self, pair_token: str) -> str:
        return f"{self.public_base_url}/m/{pair_token}"

    def ensure_dirs(self) -> None:
        self.tus_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    errors: list[str] = []

    def require(key: str) -> str:
        value = (env.get(key) or "").strip()
        if not value:
            errors.append(f"{key} is required (e.g. {key}=...)")
        return value

    def positive_int(key: str, default: int) -> int:
        raw = (env.get(key) or "").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            errors.append(f"{key} must be an integer, got {raw!r}")
            return default
        if value <= 0:
            errors.append(f"{key} must be > 0, got {value}")
            return default
        return value

    base_url = require("PUBLIC_BASE_URL").rstrip("/")
    parts = urlsplit(base_url)
    if base_url and (
        parts.scheme not in ("http", "https")
        or not parts.netloc
        or parts.query
        or parts.fragment
    ):
        errors.append(
            "PUBLIC_BASE_URL must be an absolute http(s) origin+path without query or "
            f"fragment (e.g. https://example.org), got {base_url!r}"
        )

    data_dir = require("DATA_DIR")

    hook_secret = require("HOOK_SECRET")
    if hook_secret and len(hook_secret) < MIN_HOOK_SECRET_LEN:
        errors.append(
            f"HOOK_SECRET must be at least {MIN_HOOK_SECRET_LEN} characters, got {len(hook_secret)}"
        )
    elif hook_secret and not _URL_SAFE_SECRET.match(hook_secret):
        errors.append(
            "HOOK_SECRET must be URL-safe (A-Z a-z 0-9 . _ ~ -) because it is embedded "
            "in the tusd hook URL; a value with '+', '/', '=' or spaces is corrupted in "
            "the query string and every hook would 401. `openssl rand -hex 24` is safe. "
            "(Notably, Render's Blueprint generateValue produces base64, so do not use "
            "that generated value directly.)"
        )

    default_origin = f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""
    cors_raw = (env.get("CORS_ORIGINS") or "").strip() or default_origin
    cors_origins = [origin.strip() for origin in cors_raw.split(",") if origin.strip()]

    settings = Settings(
        public_base_url=base_url,
        data_dir=Path(data_dir).expanduser(),
        pair_token_ttl_min=positive_int("PAIR_TOKEN_TTL_MIN", DEFAULT_PAIR_TOKEN_TTL_MIN),
        max_upload_bytes=positive_int("MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES),
        max_assets_per_session=positive_int(
            "MAX_ASSETS_PER_SESSION", DEFAULT_MAX_ASSETS_PER_SESSION
        ),
        hook_secret=hook_secret,
        cors_origins=cors_origins,
    )

    if errors:
        raise ConfigError("invalid configuration:\n  - " + "\n  - ".join(errors))
    return settings