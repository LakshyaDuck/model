from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import uuid

app = FastAPI()

UPLOAD_DIR = Path(__file__).parent / "uploads"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/")
async def home():
    return "hello world"


@app.get("/uploads")
async def list_uploads():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p.name for p in UPLOAD_DIR.iterdir() if p.is_file())


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix or ".bin"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"

    with target.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)

    return {"name": target.name, "size": target.stat().st_size}
