# Namma Space capture contract — quick view

`openapi.yaml` is the authoritative, machine-readable contract. This page is the fast orientation guide for people working across the React capture UI and FastAPI service.

## What the API does

1. The laptop creates a capture session.
2. It shares the returned short-lived pairing URL with the phone.
3. The phone validates that pairing token, then uploads media through tusd at `/files/`.
4. The laptop reads the session manifest, media, and live events while uploads arrive.
5. The laptop starts the preparation job when it is ready to process the session's photos and videos.
6. When the job finishes, the laptop downloads the scene GLB and renders it in Three.js.

## Endpoint map

| Area | Operations | Authentication |
| --- | --- | --- |
| Session setup | `POST /api/sessions`; `POST /api/sessions/{session_id}/pair-token` | Create: none. Rotate: owner token. |
| Phone pairing | `GET /api/pair/{pair_token}` | Pair token is in the URL; no owner token. |
| Capture state | `GET /api/sessions/{session_id}/manifest`; `GET /api/sessions/{session_id}/events` | Owner token. |
| Media | `GET /api/sessions/{session_id}/assets/{asset_id}/file`; `.../thumb` | Owner token. File supports HTTP Range. |
| Processing | `POST` and `GET /api/sessions/{session_id}/process` | Owner token. |
| Models | `GET /api/sessions/{session_id}/model`; `GET /api/sessions/{session_id}/model/collision` | Owner token; `?token=` alternative. |

## Tokens and responsibilities

- **Owner token:** returned once when a session is created. It protects reading session state, media, event streams, processing, and pairing-token rotation. Send it as `Authorization: Bearer <token>`.
- **Query-token alternative:** `/events`, `/file`, `/thumb`, `/model`, and `/model/collision` also accept `?token=<owner-token>` for `EventSource`, image, video, download, and model-loader requests that cannot set headers.
- **Pair token:** short-lived, upload-setup capability carried by the phone URL. A replacement immediately invalidates its predecessor.
- **Hook secret:** authorizes tusd's private `/internal/tusd-hook` endpoint. It is operational infrastructure, not a browser API.

## Important response concepts

- A new session returns its session id, owner token, pair token, pair expiry, and phone URL.
- A **manifest** is the current ordered list of assets: each has an id, type (`video`, `photo`, `floorplan`, or `sensor`), storage status, metadata, optional checksum, optional thumbnail, and any failure reason.
- A **processing job** is always a snapshot with status `idle`, `queued`, `running`, `done`, or `failed`, plus progress counters and output paths relative to `DATA_DIR`. `model_path` and `collision_model_path` are empty until those GLBs exist.
- The event stream begins with a `snapshot`, then publishes asset lifecycle events and processing-job events. Treat event payloads as the same manifest, asset, removal, or job shapes defined in `openapi.yaml`.

## Model delivery

Once processing has produced `artifacts/v1/scene.glb`, fetch it with
`GET /api/sessions/{session_id}/model`. The response is `model/gltf-binary`, so a
Three.js `GLTFLoader` can load it directly. The simplified
`artifacts/v1/collision.glb` is available at `GET .../model/collision` for
collision and navigation work. Both endpoints return `404` until their artifact
exists, and both accept the owner token as a bearer header or `?token=`.

```js
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { modelUrl } from './api'

new GLTFLoader().load(modelUrl(sessionId, ownerToken), (gltf) => scene.add(gltf.scene))
```

## Boundaries

This contract covers browser requests to the capture API. The resumable upload protocol is supplied by tusd at `/files/`; its required metadata is `pair_token`, `kind`, `filename`, and `filetype`. The private tusd hook and development-only routes are deliberately outside this public contract.

When a browser-visible API change is needed, change `openapi.yaml` and the relevant client/server code together. Consult `AGENTS.md` for the repository-wide working agreements.
