"""App wiring. Settings are read from the environment at startup and never guessed."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import models  # noqa: F401  - registers the tables before create_all
from .api import router as api_router
from .config import ConfigError, Settings, load_settings
from .db import Database
from .events import Broker
from .hooks import router as hooks_router
from .logging_setup import install as install_log_redaction

logger = logging.getLogger(__name__)

# DEV ONLY throwaway pages, kept in one folder so the real frontend can replace them.
DEV_PAGES = Path(__file__).resolve().parents[2] / "dev_pages"


def create_app(settings: Settings | None = None) -> FastAPI:
    # Redact tokens/hook secret before uvicorn can log a request path or query string.
    install_log_redaction()
    # Read early so CORS is correct; a bad environment still fails loudly in lifespan.
    resolved = settings
    if resolved is None:
        try:
            resolved = load_settings()
        except ConfigError as exc:
            logger.warning("deferring config error to startup: %s", exc)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings_now = settings or load_settings()
        settings_now.ensure_dirs()
        app.state.settings = settings_now
        app.state.database = Database(str(settings_now.db_path))
        app.state.broker = Broker()
        logger.info(
            "data_dir=%s base_url=%s cors=%s",
            settings_now.data_dir,
            settings_now.public_base_url,
            settings_now.cors_origins,
        )
        yield

    app = FastAPI(title="room capture backend", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        # Fail closed if the environment was unreadable: the app dies in lifespan
        # anyway, and a silent "*" is not something a misconfigured deploy should get.
        allow_origins=resolved.cors_origins if resolved else [],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(api_router)
    app.include_router(hooks_router)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict:
        return {"ok": True}

    def dev_page(name: str) -> FileResponse:
        path = DEV_PAGES / name
        if not path.is_file():
            logger.warning("dev page missing: %s", path)
        return FileResponse(path, media_type="text/html")

    @app.get("/dev/laptop", include_in_schema=False)
    async def dev_laptop() -> FileResponse:
        return dev_page("laptop.html")

    @app.get("/m/{pair_token}", include_in_schema=False)
    async def dev_phone(pair_token: str) -> FileResponse:
        return dev_page("phone.html")

    return app


app = create_app()