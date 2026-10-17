# AGENTS.md

Read this file at the start of every AI session in this repository.

## Source of truth

- `contracts/openapi.yaml` — the implemented public HTTP API: paths, request and response shapes, authentication, and status codes.
- `docs/system-design.md` — product scope, service boundaries, pipeline stages, and the implementation roadmap.
- Code and tests — the authoritative detail for behaviour not represented by the public API contract.

Read the contract and the relevant design section before changing an API consumer or provider.

## Working agreements

1. Treat `contracts/openapi.yaml` as the shared frontend-to-backend boundary. Update it in the same change as a public API change; do not guess routes, fields, enums, authentication, or status codes.
2. Keep the client boundary in `frontend/src/api.js`. Pages use its exported functions and URL helpers; it owns browser requests to `/api` and `/files`.
3. Keep public routes in `backend/src/backend/api.py`; keep tusd's private hook receiver in `backend/src/backend/hooks.py`. The hook endpoint is service-to-service infrastructure and is never exposed through the frontend client.
4. Preserve the security model: owner tokens authorize session reads and processing; pair tokens authorize upload setup; `HOOK_SECRET` authorizes tusd hooks. Do not log, persist in browser storage, or expose secret tokens beyond their existing flow.
5. Preserve the shared-volume invariant: the API and tusd use the same `DATA_DIR`, and uploaded files are finalized with an atomic move. Keep derived manifests and processing outputs beneath their session directory.
6. Keep capture and long-running reconstruction concerns separate. `docker compose up` runs capture; the COLMAP worker is an explicit `reconstruction` profile job.
7. Finish each task with a concise plain-language summary and the checks run.

## Repository map

- `frontend/` — Vite + React capture UI.
- `backend/` — FastAPI capture API, tusd hook processing, SQLite metadata, and tests.
- `contracts/` — versioned public API contract and its quick reference.
- `compose.yaml` and `deploy/` — Docker-first local topology and gateway.
- `docs/` — system design and architecture decisions.
- `scripts/` — reconstruction worker entrypoint.

## Useful checks

- `cd backend && uv run pytest`
- `cd frontend && npm run lint && npm run build`
- `docker compose up --build`

Use the smallest relevant check for the change; run both backend tests and frontend checks when a contract change affects both sides.
