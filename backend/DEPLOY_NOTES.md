You are building the backend for phase 1 (the input stage) of a 3D room-reconstruction web system. Build ONLY what is described here. Keep the repo small and readable: few files, no abstraction layers I did not ask for, no file over ~300 lines. Explain nothing in chat; put short comments in code only where the "why" is non-obvious.

## Goal
A person opens the site on a laptop and sees a QR code. They scan it with a phone, which opens a page tied to that session. They capture or pick video/photos (plus an optional floor plan and optional sensor data file) and upload them. Uploads must survive network drops (resumable). Everything uploaded appears live on the laptop. The server ends up with a per-session folder and a manifest.json that a later processing stage will read. Phone and laptop never talk directly; the server is the shared state.

## Stack (fixed)
- Python 3.12, FastAPI, SQLModel + SQLite, uvicorn, single process (no Redis, no Celery).
- Resumable uploads use the tus protocol via a separate `tusd` container (official Go server, pin v2.x). Do NOT implement tus yourself. FastAPI integrates with tusd through tusd's HTTP hooks. Read the official tusd hooks docs for the exact payload and response formats; do not guess them.
- Live updates laptop <- server: Server-Sent Events (sse-starlette), in-process asyncio pub/sub per session.
- ffmpeg and Pillow for thumbnails.
- pytest for tests.

## Security model (two tokens per session)
- `owner_token`: returned to the laptop at session creation. Required for everything the laptop does (read manifest, subscribe to events, fetch files).
- `pair_token`: short-lived (default 30 min, env-configurable), upload-only, goes in the QR URL. It can only (a) look up its session and (b) authorize creating uploads for that session. It can never read anything.
- Generate both with `secrets.token_urlsafe(24)`. Store only SHA-256 hashes of tokens in the DB.
- Pair token can be re-issued by the owner (POST) to refresh the QR; re-issuing invalidates the old one.
- Token is validated at upload creation (tusd `pre-create` hook, token sent in tus metadata). Uploads already in progress are not cut off if the token expires mid-upload.

## Data model
- Session: id, owner_token_hash, pair_token_hash, pair_expires_at, created_at.
- Asset: id, session_id, kind (video | photo | floorplan | sensor), original_filename, mime, size_bytes, sha256, status (uploading | stored | ready | failed), stored_path, thumb_path, created_at.
- Manifest: after every asset change, atomically write `DATA_DIR/sessions/<session_id>/manifest.json` (write temp file then rename) listing all assets with the fields above. SQLite is the source of truth; manifest.json is a derived export for the next pipeline stage.

## Storage layout
- tusd writes to `DATA_DIR/tus/`.
- On the post-finish hook, FastAPI MOVES the file to `DATA_DIR/sessions/<session_id>/raw/<asset_id>.<ext>` (same volume so it is a rename), computes sha256, records the mime exactly as received, then generates a thumbnail (ffmpeg first frame for video, Pillow for photos; skip for floorplan/sensor unless it is an image). Status goes uploading -> stored -> ready (or failed with reason).
- Do NOT transcode or normalize formats. Accept whatever arrives (iOS .mov/HEVC, Android .mp4/.webm, HEIC, etc.) and just record it. Normalization is a later stage.

## HTTP API (all under /api unless noted)
- POST /api/sessions -> {session_id, owner_token, pair_token, pair_expires_at, phone_url}. phone_url = PUBLIC_BASE_URL + "/m/" + pair_token.
- POST /api/sessions/{id}/pair-token (owner) -> new pair_token and phone_url.
- GET /api/pair/{pair_token} -> {session_id, expires_at} or 404/410. Used by the phone page to check the QR is valid. Reveals nothing else.
- GET /api/sessions/{id}/manifest (owner) -> current assets.
- GET /api/sessions/{id}/events (owner, SSE). On connect, first send a `snapshot` event with the full asset list (this makes reconnects safe), then live events: asset.created, asset.stored, asset.ready, asset.failed, asset.removed. Send a keep-alive comment every ~15 s.
- GET /api/sessions/{id}/assets/{asset_id}/file and .../thumb (owner). Must support HTTP Range requests so videos can seek. Verify the installed Starlette's FileResponse actually does this; if not, implement it.
- POST /internal/tusd-hook: receives tusd hooks. Handle pre-create (validate pair_token, kind, size limit, then reject or allow), post-create (create Asset as uploading, publish event), post-finish (process as above), post-terminate (mark removed). This route must NOT be reachable from outside: require a shared secret header (HOOK_SECRET) and document that the reverse proxy must not expose /internal.
- Owner token is passed as `Authorization: Bearer ...` for normal requests. For EventSource/media tags that cannot set headers, also accept it as a `?token=` query parameter on the events and file endpoints only.

## Upload metadata contract (what the phone sends with each tus upload)
`pair_token`, `kind` (video|photo|floorplan|sensor), `filename`, `filetype`. Reject unknown kinds. Enforce MAX_UPLOAD_BYTES (env, default 5 GB) and a per-session asset count limit (env, default 200).

## Config (environment variables only, validated at startup with clear errors)
PUBLIC_BASE_URL, DATA_DIR, PAIR_TOKEN_TTL_MIN, MAX_UPLOAD_BYTES, MAX_ASSETS_PER_SESSION, HOOK_SECRET, CORS_ORIGINS. Never hardcode localhost.

## Throwaway dev pages (clearly marked DEV ONLY, easy to delete)
Serve two plain HTML+JS pages (no framework, no build step) so the full flow can be tested before the real React frontend exists:
- /dev/laptop: creates a session, shows the QR (qrcode lib from a CDN is fine), subscribes to SSE, lists assets with thumbnails live.
- /m/{pair_token} (dev version): validates the token, has two file inputs (`accept="video/*,image/*" capture="environment"` and a gallery multi-select), plus optional floor plan and sensor file pickers, uploads with tus-js-client (from a CDN) with retry/resume and a visible progress bar per file.
The real frontend will replace these; keep them in one `dev_pages/` folder.

## Tests
- pytest covering: token hashing and expiry, pair-token re-issue invalidating the old one, pre-create rejection cases (bad token, expired token, bad kind, too large), post-finish processing with a small fixture file, atomic manifest writing, SSE snapshot-then-live ordering.
- `scripts/simulate_upload.py`: uploads a file to the running stack using the tus protocol with a valid pair token, so the pipeline can be tested without a phone.

## Deliverables
1. The FastAPI app (Dockerfile for the API only, ffmpeg installed in the image).
2. `DEPLOY_NOTES.md` listing: required env vars with example values, ports, the volume layout both containers must share, the exact tusd command-line flags (upload dir, hook URL, enabled hook events, base path, max size), and the routing the reverse proxy needs (which paths go to tusd, which to the API, which must be blocked). I will write docker-compose and the proxy config myself, so do NOT generate those.
3. README with how to run tests and the simulate script.

## Explicitly out of scope
User accounts/login, format normalization, frame extraction, 3D reconstruction, the real React frontend, live sensor capture from the browser, multi-worker scaling.

When done, list anything you were unsure about or had to assume.
