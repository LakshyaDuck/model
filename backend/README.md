# backend — phase 1 (capture)

FastAPI service for the input stage of room reconstruction: a laptop shows a QR code,
a phone scans it and uploads video/photos through [tus](https://tus.io), and the server
ends up with a per-session folder plus a `manifest.json` for the next stage.

Nothing is transcoded. What the phone sends is stored byte for byte and recorded.

## Layout

```
src/backend/
  main.py        app factory, CORS, dev page routes
  config.py      env-only settings, validated at startup
  models.py      SQLModel tables (sessions, assets)
  db.py          SQLite engine
  security.py    owner/pair token hashing and lookup
  api.py         public HTTP API + SSE stream
  hooks.py       /internal/tusd-hook (pre-create, post-create, post-finish, post-terminate)
  events.py      in-process pub/sub per session
  manifest.py    atomic manifest.json writer
  media.py       sha256, safe extensions, thumbnails (ffmpeg / Pillow)
  processing.py  Process job: normalizes photos into processed/inputs.json and
                 runs pipeline() (owner hook) over the session's videos
  extract_frames.py  blur-filtered frame extraction for one video (Laplacian
                     variance, CSV report) -> extracted_frames/
  feature_extraction.py  COLMAP SIFT extraction over extracted frames -> database.db
  feature_matching.py    COLMAP exhaustive matching over that database
dev_pages/       DEV ONLY throwaway laptop + phone pages
scripts/         dev.py — one-command local API+tusd stack; simulate_upload.py — phone-less upload
tests/           pytest
```

Deploy details (env vars, tusd flags, proxy routing, volume layout) are in
[DEPLOY.md](DEPLOY.md).

## Run locally

Needs `ffmpeg` on `PATH` for video thumbnails, plus a running `tusd` for real uploads.
`ffmpeg` is a system package; **tusd is not on any distro's default PATH**, so grab the
binary first:

```sh
# one-off, to ~/.local/bin (already on most PATHs); use /usr/local/bin if you prefer
mkdir -p ~/.local/bin
curl -sL https://github.com/tus/tusd/releases/download/v2.10.1/tusd_linux_amd64.tar.gz \
  | tar xz -C /tmp tusd_linux_amd64/tusd
mv /tmp/tusd_linux_amd64/tusd ~/.local/bin/tusd
tusd -version   # -> Version: v2.10.1
```

Then the whole local stack in one command:

```sh
uv run python scripts/dev.py
```

It starts the API (autoreload) and tusd together, sharing `DATA_DIR` and a dev
`HOOK_SECRET`, waits for `/healthz` before starting tusd, prints the dev URL, and stops
both on Ctrl-C. Defaults are `DATA_DIR=./data` and `PUBLIC_BASE_URL=http://<lan-ip>:8000`,
where the IP is auto-detected from the default route so a phone on the same Wi-Fi (or on
this laptop's hotspot) can scan the QR; it falls back to `localhost` if detection fails.
Override any of them in the environment, and use `--api-port` / `--tusd-port` / `--no-reload`
if needed.

Or run the two processes by hand — first the API (shell one):

```sh
uv sync
export PUBLIC_BASE_URL=http://localhost:8000 DATA_DIR=./data HOOK_SECRET=dev-secret-please-change
uv run uvicorn backend.main:app --reload
```

Then tusd (shell two), pointed at the same `DATA_DIR`:

```sh
tusd -upload-dir ./data/tus -port 1080 -base-path /files/ -max-size 5368709120 \
  -hooks-enabled-events pre-create,post-create,post-finish,post-terminate \
  -hooks-http "http://127.0.0.1:8000/internal/tusd-hook?secret=dev-secret-please-change" \
  -disable-download -disable-concatenation
```

`tusd` must run from the `backend/` directory (or point `-upload-dir` at an absolute
path) so it shares `DATA_DIR` with the API. The `\` line continuations are bash/zsh
syntax; in fish, put it on one line. If tusd exits immediately saying the hook endpoint
is unreachable, the API in the first shell is not up yet — start the API first.

Open <http://localhost:8000/dev/laptop>, press **New session**, scan the QR (or open
`/m/<pair_token>` in another browser tab), and upload.

## Tests

```sh
uv run pytest
```

No server or network needed: hooks are driven by posting real tusd hook payloads, and
the SSE tests run the app in a real uvicorn server on an ephemeral port because
`TestClient` buffers whole response bodies and would never see an event stream finish.

Covered: token hashing and expiry, pair-token rotation invalidating the old token,
pre-create rejections (bad token, expired token, bad kind, too large, too many assets),
post-finish storage/hashing/thumbnailing/idempotency/out-of-order delivery,
post-terminate cleanup, atomic manifest writes, and snapshot-then-live SSE ordering.

## Simulating an upload without a phone

Against a running stack (API on `:8000`, tusd on `:1080`):

```sh
# creates a session through the API, then uploads the file over tus
uv run python scripts/simulate_upload.py ../some.mp4 --kind video

# use an existing pair token (e.g. the one shown on /dev/laptop)
uv run python scripts/simulate_upload.py floor.png --kind floorplan --pair-token <token>

# continue an upload that died mid-way
uv run python scripts/simulate_upload.py ../some.mp4 --kind video --resume-url <upload-url>
```

Progress is printed per chunk. A rejected upload prints tusd's JSON error, which is
where the reason from the `pre-create` hook shows up.

## Dev pages

`dev_pages/` holds two dependency-free HTML pages used only to exercise the flow before
the React frontend exists. They load `qrcodejs` and `tus-js-client` from a CDN. Delete
the folder and the two routes in `main.py` when the real frontend lands.

## API

Owner token: `Authorization: Bearer <token>`. The `events` and `.../file`/`.../thumb`
endpoints also accept `?token=` because `EventSource` and media tags cannot set headers.

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/sessions` | – | Create a session, returns `owner_token` (shown once) and `phone_url`. |
| POST | `/api/sessions/{id}/pair-token` | owner | Rotate the pair token; invalidates the old QR. |
| GET | `/api/pair/{pair_token}` | – | `{session_id, expires_at}`, or 404/410. Used by the phone page. |
| GET | `/api/sessions/{id}/manifest` | owner | Current assets. |
| GET | `/api/sessions/{id}/events` | owner | SSE: `snapshot`, then `asset.created/stored/ready/failed/removed`, keep-alive comment every 15 s. |
| GET | `/api/sessions/{id}/process` | owner | Latest processing job status (`idle` when there is none). |
| POST | `/api/sessions/{id}/process` | owner | Start processing the session's photos/videos; returns `202` and the job. |
| GET | `/api/sessions/{id}/assets/{asset_id}/file` | owner | Raw file, supports Range so videos seek. |
| GET | `/api/sessions/{id}/assets/{asset_id}/thumb` | owner | JPEG thumbnail, 404 when there is none. |
| POST | `/internal/tusd-hook` | `HOOK_SECRET` | tusd hook receiver. Never expose it. |

Upload metadata the phone sends with each tus upload: `pair_token`, `kind`
(`video|photo|floorplan|sensor`), `filename`, `filetype`.