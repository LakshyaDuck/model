# Model

Minimal camera app: a Vite + React frontend that captures photos and video in the
browser and uploads them to a FastAPI backend.

## Layout

- `frontend/` — Vite + React (JavaScript, no TypeScript)
- `backend/` — FastAPI

## Run

Backend:

```sh
cd backend
uv run fastapi dev main.py
```

Frontend:

```sh
cd frontend
pnpm install
pnpm dev
```

Open http://localhost:5173. The camera prompt requires a secure context, so use
`localhost` rather than a LAN IP over plain HTTP. Frontend commands are
`pnpm dev`, `pnpm build`, and `pnpm lint`.

Captures land in `backend/uploads/`. The backend allows CORS from
`http://localhost:5173` only; set `VITE_API_URL` to point elsewhere.
