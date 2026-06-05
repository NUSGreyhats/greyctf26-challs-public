from __future__ import annotations

import os
import secrets
import string
from pathlib import Path, PurePosixPath, PureWindowsPath

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

TOKEN_LENGTH = 67
BASE_DIR = Path(__file__).resolve().parents[1]
VAULT_DIR = BASE_DIR / "vault_files"
TOKEN_FILE = BASE_DIR / ".vault_token"
DUMMY_FILENAME = "test.txt"
DUMMY_CONTENT = b"test\n"


def _generate_token() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(TOKEN_LENGTH))


def _load_token() -> str:
    env_token = os.getenv("VAULT_TOKEN", "").strip()
    if env_token:
        if len(env_token) != TOKEN_LENGTH:
            raise RuntimeError(f"VAULT_TOKEN must be exactly {TOKEN_LENGTH} characters.")
        return env_token

    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if len(token) == TOKEN_LENGTH:
            return token

    token = _generate_token()
    TOKEN_FILE.write_text(token + "\n", encoding="utf-8")
    return token


VAULT_TOKEN = _load_token()

app = FastAPI(title="Vera's Super Secret File Vaults")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

VAULT_DIR.mkdir(parents=True, exist_ok=True)


def _seed_dummy_file() -> None:
    dummy_path = VAULT_DIR / DUMMY_FILENAME
    if not dummy_path.exists():
        dummy_path.write_bytes(DUMMY_CONTENT)


_seed_dummy_file()


def _deny_bad_token(token: str | None) -> None:
    if not token or not secrets.compare_digest(token, VAULT_TOKEN):
        raise HTTPException(status_code=400, detail="Invalid vault token.")


def _download_path(filename: str | None) -> Path:
    if not filename:
        raise HTTPException(status_code=404, detail="File not found.")

    posix_name = PurePosixPath(filename).name
    windows_name = PureWindowsPath(posix_name).name
    if filename != windows_name or windows_name in {"", ".", ".."}:
        raise HTTPException(status_code=404, detail="File not found.")

    target = (VAULT_DIR / windows_name).resolve()
    if target.parent != VAULT_DIR.resolve() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    return target


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "sealed"}


@app.post("/api/vault")
async def upload_file(
    upload: str | None = Query(default=None),
    token: str | None = Query(default=None),
    file: UploadFile | None = File(default=None),
) -> PlainTextResponse:
    _deny_bad_token(token)
    return PlainTextResponse("upload successful")


@app.get("/api/vault")
def download_file(
    upload: str | None = Query(default=None),
    download: str | None = Query(default=None),
    token: str | None = Query(default=None),
):
    _deny_bad_token(token)
    if upload is not None:
        return PlainTextResponse("upload successful")

    target = _download_path(download)
    return FileResponse(
        target,
        media_type="application/octet-stream",
        filename=target.name,
    )
