"""Configuration comes from the environment plus an optional `backend/.env`.

These tests never read the developer's real `backend/.env`: every test either passes
an explicit mapping or points `load_settings` at a temporary file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.config import (
    DEFAULT_ENV_FILE,
    DEFAULT_MAX_ASSETS_PER_SESSION,
    DEFAULT_MAX_UPLOAD_BYTES,
    DEFAULT_PAIR_TOKEN_TTL_MIN,
    ConfigError,
    load_settings,
)

HOOK_SECRET = "test-hook-secret-0123456789"
_ALL_KEYS = (
    "PUBLIC_BASE_URL",
    "DATA_DIR",
    "HOOK_SECRET",
    "PAIR_TOKEN_TTL_MIN",
    "MAX_UPLOAD_BYTES",
    "MAX_ASSETS_PER_SESSION",
    "CORS_ORIGINS",
)


def _clear_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _ALL_KEYS:
        monkeypatch.delenv(key, raising=False)


def _write_env_file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "backend.env"
    path.write_text(text, encoding="utf-8")
    return path


def test_default_env_file_is_the_backend_directory_not_the_cwd():
    # tests/ -> backend/.env, regardless of where pytest was launched.
    assert DEFAULT_ENV_FILE == Path(__file__).resolve().parents[1] / ".env"


def test_loads_values_from_dotenv_file(tmp_path, monkeypatch):
    _clear_environment(monkeypatch)
    env_file = _write_env_file(
        tmp_path,
        "\n".join(
            [
                "# local settings",
                "PUBLIC_BASE_URL=https://capture.example.org/",
                "DATA_DIR=./data",
                f"HOOK_SECRET={HOOK_SECRET}",
                "PAIR_TOKEN_TTL_MIN=45",
            ]
        ),
    )

    settings = load_settings(env_file=env_file)

    assert settings.public_base_url == "https://capture.example.org"
    assert settings.data_dir == Path("./data")
    assert settings.hook_secret == HOOK_SECRET
    assert settings.pair_token_ttl_min == 45
    assert settings.max_upload_bytes == DEFAULT_MAX_UPLOAD_BYTES
    assert settings.max_assets_per_session == DEFAULT_MAX_ASSETS_PER_SESSION
    # CORS defaults to the PUBLIC_BASE_URL origin.
    assert settings.cors_origins == ["https://capture.example.org"]


def test_operating_system_environment_overrides_dotenv_file(tmp_path, monkeypatch):
    _clear_environment(monkeypatch)
    env_file = _write_env_file(
        tmp_path,
        "\n".join(
            [
                "PUBLIC_BASE_URL=https://file.example.org",
                "DATA_DIR=./file-data",
                "HOOK_SECRET=file-secret-0123456789",
            ]
        ),
    )
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://os.example.org")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "os-data"))
    monkeypatch.setenv("HOOK_SECRET", "os-secret-0123456789")

    settings = load_settings(env_file=env_file)

    assert settings.public_base_url == "https://os.example.org"
    assert settings.data_dir == tmp_path / "os-data"
    assert settings.hook_secret == "os-secret-0123456789"


def test_explicit_environment_bypasses_dotenv_file(tmp_path):
    # Even a broken file cannot affect a caller that already resolved its config.
    env_file = _write_env_file(tmp_path, "PUBLIC_BASE_URL=not-a-url\nDATA_DIR=\nHOOK_SECRET=\n")

    settings = load_settings(
        {
            "PUBLIC_BASE_URL": "https://explicit.example.org",
            "DATA_DIR": "/explicit-data",
            "HOOK_SECRET": HOOK_SECRET,
        },
        env_file=env_file,
    )

    assert settings.public_base_url == "https://explicit.example.org"


def test_missing_required_variables_are_reported_together():
    with pytest.raises(ConfigError) as error:
        load_settings({})

    message = str(error.value)
    assert "PUBLIC_BASE_URL is required" in message
    assert "DATA_DIR is required" in message
    assert "HOOK_SECRET is required" in message
    assert "backend/.env" in message


@pytest.mark.parametrize(
    "base_url",
    [
        "not-a-url",
        "ftp://capture.example.org",
        "https://capture.example.org?debug=1",
        "https://capture.example.org#fragment",
    ],
)
def test_invalid_public_base_url_is_rejected(base_url):
    with pytest.raises(ConfigError, match="PUBLIC_BASE_URL must be an absolute http"):
        load_settings(
            {
                "PUBLIC_BASE_URL": base_url,
                "DATA_DIR": "./data",
                "HOOK_SECRET": HOOK_SECRET,
            }
        )


def test_invalid_optional_integer_is_rejected():
    with pytest.raises(ConfigError, match="PAIR_TOKEN_TTL_MIN must be an integer"):
        load_settings(
            {
                "PUBLIC_BASE_URL": "https://capture.example.org",
                "DATA_DIR": "./data",
                "HOOK_SECRET": HOOK_SECRET,
                "PAIR_TOKEN_TTL_MIN": "soon",
            }
        )


@pytest.mark.parametrize("kind", ["relative", "absolute"])
def test_data_directory_paths_are_usable_and_directories_are_created(tmp_path, monkeypatch, kind):
    monkeypatch.chdir(tmp_path)
    data_dir = "./data" if kind == "relative" else str(tmp_path / "absolute-data")
    expected = Path(data_dir) if kind == "relative" else tmp_path / "absolute-data"

    settings = load_settings(
        {
            "PUBLIC_BASE_URL": "http://localhost:8000",
            "DATA_DIR": data_dir,
            "HOOK_SECRET": HOOK_SECRET,
        }
    )
    assert settings.data_dir == expected

    settings.ensure_dirs()

    assert settings.tus_dir.is_dir()
    assert settings.sessions_dir.is_dir()
    assert settings.db_path == expected / "app.db"
