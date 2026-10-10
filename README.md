# Model

3D room reconstruction, one stage at a time.

## Layout

- `backend/` — phase 1 capture backend (FastAPI + tusd). See [backend/README.md](backend/README.md)
  for running it, testing it, and [backend/DEPLOY.md](backend/DEPLOY.md) for deployment.
- `frontend/` — Vite + React (JavaScript, no TypeScript)

## Phase 1 (backend)

The laptop creates a session and shows a QR code, the phone scans it and uploads
video/photos through tus, and the server produces a per-session folder plus a
`manifest.json` for the next stage. Two throwaway dev pages
(`/dev/laptop` and `/m/<pair_token>`) exercise the whole flow before the real
frontend exists.

```sh
cd backend
uv sync
uv run uvicorn backend.main:app --reload   # needs PUBLIC_BASE_URL, DATA_DIR, HOOK_SECRET
uv run pytest
```

The previous plain `POST /upload` endpoint and `backend/uploads/` are gone; uploads
now go through tusd.