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
  processing.py  Process job manager: normalizes photos into processed/inputs.json
                 and runs pipeline.run over the session's videos
  pipeline/      reconstruction pipeline: shared paths, photo prep, and stages
    __init__.py            public pipeline API
    paths.py               session directory layout shared by the job and stages
    prepare.py             photo normalization -> processed/images
    run.py                 pipeline() orchestration + PIPELINE_DONE
    extract_frames.py      blur-filtered frame extraction for one video (Laplacian
                           variance, CSV report) -> extracted_frames/
    feature_extraction.py  COLMAP SIFT extraction over extracted frames -> database.db
    feature_matching.py    COLMAP exhaustive matching over that database
    mapper.py              COLMAP incremental mapping -> sparse model directories
    model_analyzer.py      model statistics for a sparse model (model_analyzer CLI)
    dense_reconstruction.py COLMAP dense (CUDA) or OpenMVS CPU fallback -> point cloud
    freeze.py              versioned artifact export -> artifacts/v1/{fused.ply,poses/}
    clean_point_cloud.py   outlier removal + voxel downsample -> artifacts/v1/cleaned.ply
    align.py               plane segmentation + rotation to +Z -> artifacts/v1/aligned.ply
    mesh.py                Poisson surface reconstruction -> artifacts/v1/mesh.ply
    split.py               visual/collision meshes -> artifacts/v1/{visual,collision}.ply
    export.py              web-ready GLBs -> artifacts/v1/{scene,collision}.glb
dev_pages/       DEV ONLY throwaway laptop + phone pages
scripts/         dev.py — one-command local API+tusd stack; simulate_upload.py — phone-less
                 upload; reconstruct.sh — on-demand COLMAP reconstruction worker;
                 condition_checker.py — tail/parse pipeline stage logs
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

Covered: pipeline stage log emission and the condition-checker log parser, token
hashing and expiry, pair-token rotation invalidating the old token,
pre-create rejections (bad token, expired token, bad kind, too large, too many assets),
post-finish storage/hashing/thumbnailing/idempotency/out-of-order delivery,
post-terminate cleanup, atomic manifest writes, snapshot-then-live SSE ordering, and
owner-token GLB serving.

## Pipeline logs

Every pipeline stage writes one structured line, so a failed run is diagnosable
without opening the database:

```
pipeline stage=mesh status=start session=<id> model=0
pipeline stage=mesh status=ok session=<id> elapsed_ms=1234 model=0
pipeline stage=dense status=skipped session=<id> reason=no_backend model=0
```

Tail a live stack and show a compact timeline:

```sh
# from the repo root
docker compose logs -f api | python3 backend/scripts/condition_checker.py --session <id>

# or let the checker run compose itself
cd backend && uv run python scripts/condition_checker.py --compose --session <id>

# or inspect a saved log
cd backend && uv run python scripts/condition_checker.py --file /tmp/api.log
```

The checker ignores unrelated log lines, filters by session, prints `START`/`OK`/
`SKIP`/`FAILED` per stage, and exits non-zero when a stage fails or starts but never
finishes. It also warns when `pipeline` reports `ok` without an `export` stage, which
means the run produced no GLB.

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

Owner token: `Authorization: Bearer <token>`. The `events`, `.../file`, `.../thumb`,
and `.../model` endpoints also accept `?token=` because `EventSource`, media tags, and
model loaders cannot set headers.

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/sessions` | – | Create a session, returns `owner_token` (shown once) and `phone_url`. |
| POST | `/api/sessions/{id}/pair-token` | owner | Rotate the pair token; invalidates the old QR. |
| GET | `/api/pair/{pair_token}` | – | `{session_id, expires_at}`, or 404/410. Used by the phone page. |
| GET | `/api/sessions/{id}/manifest` | owner | Current assets. |
| GET | `/api/sessions/{id}/events` | owner | SSE: `snapshot`, then `asset.created/stored/ready/failed/removed`, keep-alive comment every 15 s. |
| GET | `/api/sessions/{id}/process` | owner | Latest processing job status (`idle` when there is none). |
| POST | `/api/sessions/{id}/process` | owner | Start processing the session's photos/videos; returns `202` and the job. |
| GET | `/api/sessions/{id}/model` | owner | `scene.glb` (`model/gltf-binary`), 404 until processing produces it. |
| GET | `/api/sessions/{id}/model/collision` | owner | `collision.glb` (`model/gltf-binary`), 404 until processing produces it. |
| GET | `/api/sessions/{id}/assets/{asset_id}/file` | owner | Raw file, supports Range so videos seek. |
| GET | `/api/sessions/{id}/assets/{asset_id}/thumb` | owner | JPEG thumbnail, 404 when there is none. |
| POST | `/internal/tusd-hook` | `HOOK_SECRET` | tusd hook receiver. Never expose it. |

Upload metadata the phone sends with each tus upload: `pair_token`, `kind`
(`video|photo|floorplan|sensor`), `filename`, `filetype`.