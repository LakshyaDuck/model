# Deploy notes — phase 1 capture backend

Two containers, one public origin, one shared volume:

```
phone ──scan QR──> phone page (API) ──tus──> tusd ──hook──> API
laptop ──API (owner token)──> API <──SSE──┘          │
                                     └── moves files into DATA_DIR/sessions/──> manifest.json
```

You write docker-compose and the proxy config; this file lists what they must contain.

## 1. Environment variables (API container)

| Variable | Required | Example | Notes |
| --- | --- | --- | --- |
| `PUBLIC_BASE_URL` | yes | `https://capture.example.org` | No trailing slash. Used to build `phone_url` = `PUBLIC_BASE_URL + /m/<pair_token>`. Must be the origin users actually visit, not an internal container name. |
| `DATA_DIR` | yes | `/data` | Must be the **same volume** tusd writes to. Must be writable by both containers (same uid, or a shared group). |
| `HOOK_SECRET` | yes | `openssl rand -hex 24` | ≥ 16 chars, **URL-safe** (A-Z a-z 0-9 . _ ~ -). Shared with tusd via the hook URL. |
| `PAIR_TOKEN_TTL_MIN` | no (30) | `45` | How long a scanned QR stays valid. Re-issue refreshes it. |
| `MAX_UPLOAD_BYTES` | no (5368709120) | `5368709120` | Keep **identical** to tusd's `-max-size`. Enforced in both places. |
| `MAX_ASSETS_PER_SESSION` | no (200) | `200` | Counted at upload creation. |
| `CORS_ORIGINS` | no (origin of `PUBLIC_BASE_URL`) | `https://capture.example.org,https://app.example.org` | Comma separated, or `*`. Only needed if the real frontend is served from a different origin than the API. |

Missing or malformed values fail at startup with a message naming the variable; nothing is guessed and no localhost is ever assumed.

There is a ready-made, non-secret template in [`.env.example`](.env.example) — copy it
to `.env` and fill in the values.

## 1a. What is actually a secret

**Only `HOOK_SECRET`.** It is the one value that must go in your secret manager /
compose `env_file` and must never be committed. `PUBLIC_BASE_URL`, `DATA_DIR`, and the
tuning knobs are configuration, not secrets.

Generate it once, on whatever machine you like, and give the **same value to both
services** — a mismatch makes every hook 401:

```sh
openssl rand -hex 24        # 48 hex chars, always URL-safe
```

It must be **URL-safe** (A-Z a-z 0-9 . _ ~ -). The secret is embedded in the tusd hook
URL, and a `+` (which base64 contains) is decoded as a space in a query string, so the
hook would fail. Startup rejects a non-URL-safe secret with a message saying so. In
particular, **Render's Blueprint `generateValue: true` produces base64 — do not use that
generated value directly.** On Render, either set the dashboard/synced value to your own
hex secret on both services, or put the secret in an Environment Group linked to both.
The two services can also share one generated value without you handling it, but only if
that value is URL-safe.


| Value | Where it lives | If it leaks |
| --- | --- | --- |
| `HOOK_SECRET` | env, shared with tusd | anyone who can reach `/internal/tusd-hook` can forge uploads. Rotate it in both places. |
| owner token | generated per session, returned once, stored **hashed** | full read access to that session. Rotate by creating a new session. |
| pair token | generated, stored **hashed**, short lived | upload-only, into one session, until it expires. |
| the SQLite DB + `DATA_DIR` | the volume | contains token **hashes** (not tokens) and the uploaded media. The media is the sensitive part: protect the volume. |

What the code does so these do not leak by accident:

- **Access logs are redacted.** The hook secret rides in the tusd hook URL, the owner
  token can ride in `?token=`, and the pair token is a URL path segment (`/m/<token>`).
  `logging_setup.py` rewrites `secret=…`, `token=…`, `/m/<token>` and
  `/api/pair/<token>` to `REDACTED` on every log record, so `uvicorn`'s access log and
  anything scraping it never sees a usable credential.
- **Only hashes are stored** for owner/pair tokens (SHA-256, `hmac.compare_digest` on
  lookup), so a copied `app.db` cannot be replayed.
- **The hook secret is compared with `hmac.compare_digest`**, not `==`.
- The startup log prints `data_dir`, `base_url`, and `cors` — **not** `hook_secret`.

Still on you:

- **tusd logs its own hook URL, secret included,** as its first startup line
  (`Using 'http://…/internal/tusd-hook?secret=…'`). There is no flag to redact it.
  Treat the tusd container's **startup** log as sensitive, or point `-hooks-http` at a
  URL whose secret is injected by the proxy instead (see §6).
- Do not put `HOOK_SECRET` on a public command line that ends up in shell history; pass
  it through the compose file / env.
- Do not publish `/metrics` (tusd) or `/internal/*` (API) — see §5.

## 2. Ports

| Service | Container port | Public? |
| --- | --- | --- |
| API (FastAPI/uvicorn) | `8000` | yes, through the proxy |
| tusd | `1080` (`-host 0.0.0.0 -port 1080`) | only through the proxy, under `/files/` |
| `GET /healthz` on the API | `8000` | yes, useful for compose healthchecks |

Both containers must be on a network where tusd can reach `http://api:8000` and the API can read/write the same volume. Nothing else should reach port 1080.

## 3. Shared volume layout

One volume, mounted at `/data` in both containers:

```
/data/
├── app.db                              # SQLite, created by the API (source of truth)
├── tus/                                # tusd's upload dir (-upload-dir /data/tus)
│   └── <upload_id>, <upload_id>.info   # in-flight and finished upload data
└── sessions/<session_id>/
    ├── manifest.json                   # rewritten atomically after every asset change
    ├── raw/<asset_id>.<ext>            # moved here from tus/ on post-finish
    └── thumbs/<asset_id>.jpg
```

`DATA_DIR/tus` and `DATA_DIR/sessions` **must be the same filesystem** — `post-finish` moves the upload with `os.replace` (a rename). Two separate volumes mounted at `/data/tus` and `/data/sessions` would turn that into a multi-gigabyte copy. A single bind mount or named volume satisfies this.

tusd's leftover `<upload_id>.info` files are harmless; the API never reads them.

## 4. tusd command line

Image: `tusproject/tusd:v2.10.1` (pin a v2.x tag; check the exact published tag before building). The API in `Dockerfile` must be able to resolve the hostname `api` on the shared network.

```sh
tusd \
  -host 0.0.0.0 \
  -port 1080 \
  -upload-dir /data/tus \
  -base-path /files/ \
  -max-size 5368709120 \
  -hooks-enabled-events pre-create,post-create,post-finish,post-terminate \
  -hooks-http "http://api:8000/internal/tusd-hook?secret=$HOOK_SECRET" \
  -hooks-http-timeout 300s \
  -hooks-http-retry 3 \
  -disable-download \
  -disable-concatenation \
  -behind-proxy \
  -network-timeout 300s \
  -expose-metrics=false
```

Flag by flag:

| Flag | Why |
| --- | --- |
| `-base-path /files/` | Upload creation lives at `POST /files/`, so the proxy can send everything else to the API. Must match the `endpoint` the client uses. |
| `-max-size` | Same value as `MAX_UPLOAD_BYTES`; tusd enforces it during `PATCH` even when a client defers the length. |
| `-hooks-enabled-events` | Only the four hooks the API implements. Dropping `post-receive` removes a hook call per chunk, which matters on mobile. |
| `-hooks-http` | tusd sends **no custom headers**, so `HOOK_SECRET` has to travel in the URL query. See §6. |
| `-hooks-http-timeout 300s` | The default 15 s is too short: `post-finish` hashes the whole file and runs ffmpeg. Exceeding it makes tusd retry the hook (the API's `post-finish` is idempotent, so a retry is safe). |
| `-disable-download` | Without it anyone holding an upload URL could `GET` the raw file. Clients only need `POST`/`PATCH`/`HEAD`/`DELETE`. |
| `-disable-concatenation` | Partial uploads would otherwise finish and be processed as if they were whole files. |
| `-behind-proxy` | Makes tusd honour `X-Forwarded-*`, so the `Location` it hands the phone is a reachable public URL. |
| `-network-timeout 300s` | A phone that backgrounds the browser tab mid-upload would otherwise hit the 60 s default and lose the connection. |
| `-expose-metrics=false` | Keeps `/metrics` off the public surface; flip it on and block the path if you want Prometheus. |

Never enable `-hooks-dir` or `-hooks-grpc`: tusd supports exactly one hook handler.

## 5. Proxy routing

| Path | Goes to | Notes |
| --- | --- | --- |
| `/files/*` | tusd | tus protocol only: `POST`, `HEAD`, `PATCH`, `DELETE`, `OPTIONS`. |
| `/api/*` | API | |
| `/m/*` | Frontend | Phone scanner SPA route produced by `phone_url` (`/m/<pair-token>`). |
| `/phone/*` | Frontend | Compatibility alias for the same scanner route. |
| `/dev/*` | API | DEV ONLY throwaway laptop page. Drop this route once the real frontend exists. |
| `/healthz` | API | |
| `/internal/*` | **blocked** | tusd hook receiver. Must never be reachable from outside the compose network. tusd reaches it by container name, not through the proxy. |
| `/metrics` | **blocked** | Not published with the flags above; block it anyway. |
| `OPTIONS /files/*` | tusd | tusd answers its own CORS preflight; don't answer it in the proxy. |

Two proxy settings matter for uploads, and getting them wrong silently breaks resumability:

- **Disable request buffering** on `/files/*` (nginx: `proxy_request_buffering off;`). If the proxy reads a whole 5 GB body before forwarding, the phone cannot resume and memory blows up.
- **Raise the body size limit** on `/files/*` to at least `MAX_UPLOAD_BYTES`, and disable any proxy-level request timeout that is shorter than the upload.

Also forward `X-Forwarded-Host` / `X-Forwarded-Proto` to tusd (it needs them with `-behind-proxy`), and do **not** rewrite `/files/` on the way to tusd — the `Location` header tusd returns must stay valid for the phone.

## 6. The hook secret

`/internal/tusd-hook` rejects anything without `HOOK_SECRET` (401). tusd's HTTP hook implementation sets only `Content-Type` plus headers you explicitly forward, so there are two ways to deliver the secret:

1. **In the hook URL** (what the flags above assume): `-hooks-http "http://api:8000/internal/tusd-hook?secret=$HOOK_SECRET"`.
2. **Injected by your reverse proxy** as `X-Hook-Secret:` if you would rather not put it in a command line (it then shows up in `ps` inside the container). The API accepts either.

Keep the endpoint unreachable from outside regardless: it is the only way in that does not require a token.

## 7. Behaviour worth knowing

- **Pair tokens are upload-only and short lived.** `POST /api/sessions/{id}/pair-token` (owner) rotates it, which invalidates the printed QR. A rotated or expired token does **not** cut off uploads that are already running: at creation the API hands tusd the `session_id` and `asset_id` in the upload metadata, so later hooks never look at the token again.
- **The manifest is a derived export.** SQLite is the source of truth; `manifest.json` is rewritten (temp file + rename) after every asset change. Paths inside it are relative to `DATA_DIR`.
- **`post-terminate` means "cancel an unfinished upload".** tusd answers `204` to the
  phone's `DELETE` and fires the hook, which drops the `uploading` row from the manifest.
  Deleting an upload that already *finished* gets `404` and no hook, because tusd has
  already handed that data to `post-finish` — at that point the file in
  `sessions/<id>/raw/` is the artifact and there is nothing left to cancel.
- **An upload that dies and is never resumed stays `uploading` forever.** tusd fires
  `post-terminate` only on an explicit `DELETE`, so a phone that loses its upload mid-way
  leaves one row in `status: uploading` and one `<upload_id>.info` in `DATA_DIR/tus`. It is
  inert (no file, no bytes), it is still resumable by the phone with `upload.findPreviousUploads`,
  and cleaning it up needs a reaper that phase 1 does not have. If that matters later, sweep
  `status = 'uploading'` rows older than a day; do not delete the `.info` files out from under
  a phone that may still resume.
- **Assets are never transcoded.** Whatever the phone sends is stored byte for byte and the mime is recorded as received. HEIC and HEVC get no thumbnail; the asset is still `ready`, just without a thumb.
- **Thumbnails are best effort.** ffmpeg/Pillow failures are logged and leave `thumb_path` null.
- **Single process only.** The SSE broker is in memory; do not run multiple API workers.
- **Phase 1 scope.** No accounts, no normalisation, no frame extraction, no reconstruction.

## 8. Render specifics

This section records why Render is *not* the host. The chosen deployment is a plain
free-tier VM running the two-container compose layout from §2–§5 as-is. Keep this section
so nobody re-discovers the trap later.

Render does not map onto the two-container compose layout in §2–§5. Three platform
rules decide the topology, and all three point the same way:

1. **One public HTTP port per web service.** Render injects `PORT` (default `10000`) and
   scans *that* port; a container that only listens on `8000` is invisible. The image now
   binds `0.0.0.0:$PORT`, and you must set the health check path to `/healthz` (there is no
   `/` route). You still cannot expose the API and tusd as two paths on one service — only
   one port is reachable.
2. **A persistent disk attaches to exactly one service and is not shared.** So "API service
   + tusd service, shared volume" is impossible: two services have two disks, and the
   `post-finish` rename from `/data/tus` to `/data/sessions` crosses filesystems and fails.
3. **The Free compute plan has no disks and an ephemeral filesystem.** Local files (the
   SQLite DB *and* all media) are lost on every deploy, restart, and 15-minute idle
   spin-down. Do not run this backend on a Free web service.

Net: on Render this belongs in **one web service** running the API, tusd, *and* a small
reverse proxy that listens on `$PORT` (routes `/files/*` → tusd locally, blocks `/internal/*`,
forwards everything else to the API), with a single **paid** instance and one persistent
disk mounted at `/data`. That is also the only way item 1 and item 2 both hold. A Render
Blueprint can express the service and the disk; it cannot express a second shareable volume.

`HOOK_SECRET` must be the same URL-safe value everywhere (§1a). If tusd runs in the same
container, its hook URL is just `http://127.0.0.1:8000/internal/tusd-hook?secret=$HOOK_SECRET`
and never needs to leave the box.

## 9. Domain, DNS, and TLS

The deployment host is `shares.qzz.io`. `qzz.io` is a DigitalPlat FreeDomain (free
subdomain) zone served by its own nameservers (`ns1/ns2/ns3.qzz.io`), so it is **not**
Cloudflare-proxied unless you deliberately move it there.

DNS is not configured yet, and Caddy cannot get a certificate until it is. Order matters:

1. Sign in to the DigitalPlat domain dashboard, open `shares.qzz.io` → **DNS Records**, and
   add an **`A`** record pointing at the VM's public IPv4 (add `AAAA` only if the VM has
   IPv6). In that editor the **Name is relative to the zone**: use `@` for `shares.qzz.io`
   itself — typing the full `shares.qzz.io` fails with "Record names must stay inside this
   DNS zone". A name like `www` would be `www.shares.qzz.io`. Only the Name must stay
   in-zone; the value (an IP, or a CNAME target) can point anywhere.
2. Open inbound `80` and `443` on the VM.
3. Confirm it resolves *before* starting Caddy: `dig +short shares.qzz.io` must return the
   VM IP. Caddy's HTTP-01 challenge fails and backs off until it does.

Then set `PUBLIC_BASE_URL=https://shares.qzz.io` (no trailing slash). `CORS_ORIGINS` can
stay empty — it defaults to that same origin, and the dev pages are same-origin anyway.
Caddy then fetches and renews the certificate automatically.

Proxying caveat, only if you later put this host behind Cloudflare: a **proxied** (orange)
record caps request bodies at **100 MB** on Free/Pro and returns `413` for larger tus
uploads, so use **DNS-only (grey cloud)**. Cloudflare Tunnel has the same cap.


