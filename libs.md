# Libraries and services

Every third-party dependency and external service this project relies on, and
where it is declared or installed. Update this file in the same change that adds,
removes, or upgrades one.

## Backend Python (`backend/pyproject.toml`)

Declared dependencies (resolved in `backend/uv.lock`, installed into
`backend/.venv` by `uv sync`):

| Package | Version | Role |
| --- | --- | --- |
| `fastapi[standard]` | `>=0.141.1` | HTTP API and SSE; brings uvicorn, pydantic, httpx tooling |
| `sqlmodel` | `>=0.0.30` | SQLite metadata models for sessions, tokens, and assets |
| `sse-starlette` | `>=2.4.1` | Session event stream (`GET .../events`) |
| `pillow` | `>=11.0.0` | Photo thumbnails |
| `opencv-python` | `>=4.10.0` | Image normalisation and frame handling |
| `numpy` | `>=2.0` | Explicit array base for image/geometry work (also a transitive dep) |
| `open3d` | `>=0.20.0` | Geometry processing for reconstruction/rendering stages |
| `trimesh` | `>=5.1.1` | Mesh loading, inspection, and export for reconstruction stages |

Dev group (`uv sync --group dev`):

| Package | Version | Role |
| --- | --- | --- |
| `pytest` | `>=8.3` | Test runner |
| `pytest-asyncio` | `>=0.24` | Async test support (`asyncio_mode = "auto"`) |
| `httpx` | `>=0.28` | HTTP client used by API tests |

`numpy`, `open3d`, and `trimesh` were added for the preparation and
reconstruction/rendering stages. `open3d` is a large wheel (~380 MB download,
~100 MB+ in the image) and pulls its own transitive set (dash, plotly, flask,
ipython); the API image grows accordingly.

## System binaries

| Binary | Where | Role |
| --- | --- | --- |
| `ffmpeg` | `backend/Dockerfile` (`apt-get install ffmpeg`) and host `PATH` | Video thumbnail first-frame extraction |
| `libgl1`, `libglib2.0-0` | `backend/Dockerfile` | Runtime libraries `opencv-python` links against |
| `uv` | `backend/Dockerfile` (`ghcr.io/astral-sh/uv:0.12.10`) | Dependency install in the image |
| `tusd` | Not on distro PATH; its own image in `compose.yaml` | Resumable mobile uploads |
| `COLMAP` | `colmap/colmap` image, `reconstruction` profile | Sparse reconstruction worker |

## Frontend (`frontend/package.json`)

Dependencies:

| Package | Version | Role |
| --- | --- | --- |
| `react`, `react-dom` | `^19.2.8` | Capture UI |
| `react-router-dom` | `^7.18.4` | Routing between laptop/phone pages |
| `tailwindcss`, `@tailwindcss/vite` | `^4.3.3` | Styling |
| `qrcode.react` | `^4.2.0` | Pairing QR code |
| `@zxing/browser`, `@zxing/library` | `^0.1.5`, `^0.21.3` | QR scanning on the phone |
| `tus-js-client` | `^4.3.1` | Resumable uploads from the browser |

Dev dependencies: `vite`, `@vitejs/plugin-react`, `vite-plugin-mkcert`,
`eslint` (+ `@eslint/js`, react-hooks, react-refresh, `globals`), and the React
type packages.

## Services (`compose.yaml`)

| Service | Image / build | Public | Role |
| --- | --- | --- | --- |
| `gateway` | `caddy:2.10.2-alpine` | `localhost:8080` | Single origin; routes static UI, `/api`, `/files` |
| `frontend` | `./frontend` | no | Production-built React SPA |
| `api` | `./backend` | no | Sessions, tokens, manifest, SSE, tusd hooks |
| `tusd` | `tusproject/tusd:v2.10.1` | no | Resumable mobile uploads |
| `colmap` | `colmap/colmap:latest` (profile `reconstruction`) | no | One-shot sparse reconstruction worker |

The API image also installs `ffmpeg`; COLMAP is downloaded by Docker on first use
of the `reconstruction` profile.

## Checks after changing this list

- Backend: `cd backend && uv run pytest`
- Frontend: `cd frontend && npm run lint && npm run build`
- Full topology: `docker compose up --build`
