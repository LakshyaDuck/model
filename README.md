# Namma Space

3D indoor-space reconstruction, one stage at a time. The project begins with a
reliable mobile capture pipeline, then adds an isolated COLMAP reconstruction worker,
a photorealistic web scene, POIs, and obstacle-aware navigation.

## Run the local Docker stack

Docker Compose is the primary local environment. It runs the React app, FastAPI API,
tusd, and a single public gateway at <http://localhost:8080>.

```sh
cp .env.example .env
docker compose up --build
```

For phone capture, change `PUBLIC_BASE_URL` in `.env` to the laptop's reachable LAN
address (for example `http://192.168.1.20:8080`) before starting the stack. This is
the origin of the React app — the pairing URL is `PUBLIC_BASE_URL/m/<pair-token>`. A
phone cannot open a QR code pointing at `localhost`.

When running the frontend with `npm run dev` (Vite on port 5173) instead of Docker,
set `PUBLIC_BASE_URL` to the Vite origin, for example
`http://192.168.1.20:5173`. Vite already listens on all interfaces.

The COLMAP worker is intentionally on demand. After a session has at least two JPEG
or PNG photos, run:

```sh
docker compose --profile reconstruction run --rm colmap --session <session-id>
```

Docker downloads the official `colmap/colmap` image automatically the first time this
command runs. The default worker is CPU-safe and writes a sparse model and PLY point
cloud to the session's `reconstruction/colmap` directory. It is the camera-calibration
stage, not yet the final photorealistic web scene. See [the system design](docs/system-design.md)
for the complete architecture, capture SOP, and staged path to POIs/navigation.

## Layout

- `backend/` — phase 1 capture backend (FastAPI + tusd). See [backend/README.md](backend/README.md)
  for running it, testing it, and [backend/DEPLOY.md](backend/DEPLOY.md) for deployment.
- `frontend/` — Vite + React (JavaScript, no TypeScript)
- `compose.yaml` — local deploy topology (gateway, frontend, API, tusd, worker profile)
- `docs/system-design.md` — architecture, SOP, pipeline, and delivery roadmap

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
