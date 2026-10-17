# API only. tusd runs as its own container; they share the DATA_DIR volume.
FROM python:3.12-slim

# ffmpeg is a hard requirement: video thumbnails are made with it.
# libgl1 + libglib2.0-0 are the runtime libraries opencv-python links against.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app

# Dependencies first so code edits do not invalidate the install layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

COPY dev_pages ./dev_pages
COPY scripts ./scripts

ENV DATA_DIR=/data
ENV PATH="/app/.venv/bin:$PATH"
RUN mkdir -p /data
VOLUME ["/data"]
# Advisory only. Render (and most PaaS) route to the port in $PORT, which overrides
# this; docker-compose falls back to 8000.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s \
    CMD ["python", "-c", "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/healthz')"]

# Bind 0.0.0.0:$PORT so the same image works on Render (PORT=10000) and compose (8000).
# ONE process on purpose: the SSE broker and the tus hook state live in memory, so
# never add --workers.
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
