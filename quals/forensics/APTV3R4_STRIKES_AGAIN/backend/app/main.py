from __future__ import annotations

import os
import secrets
import string
from pathlib import Path, PurePosixPath, PureWindowsPath

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse

TOKEN_LENGTH = 67
BASE_DIR = Path(__file__).resolve().parents[1]
VAULT_DIR = BASE_DIR / "vault_files"
TOKEN_FILE = BASE_DIR / ".vault_token"
DUMMY_FILENAME = "test.txt"
DUMMY_CONTENT = b"test\n"
MEMDUMP_FILENAME = "mem_dump.dmp"
R2_TRUSTED_LINK = os.getenv(
    "MEMDUMP_R2_LINK",
    "https://2f0eeec84b659c3461a7b6f3eb727d4b.r2.cloudflarestorage.com/greyctf26/b5637bd1997e524a056cd4611cfd7c43/mem_dump.zip?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=e8894ef8d1c88b418ccd644073b4e57b%2F20260528%2Fus-east-1%2Fs3%2Faws4_request&X-Amz-Date=20260528T161423Z&X-Amz-Expires=259200&X-Amz-SignedHeaders=host&X-Amz-Signature=253ef6700bb2113a80ca0612f53e220102ecf6bbc0986cd7d5060cde3b60719b"
).strip()


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


def _vault_filename(filename: str | None) -> str:
    if not filename:
        raise HTTPException(status_code=404, detail="File not found.")

    posix_name = PurePosixPath(filename).name
    windows_name = PureWindowsPath(posix_name).name
    if filename != windows_name or windows_name in {"", ".", ".."}:
        raise HTTPException(status_code=404, detail="File not found.")

    return windows_name


def _download_path(filename: str) -> Path:
    target = (VAULT_DIR / filename).resolve()
    if target.parent != VAULT_DIR.resolve() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    return target


def _remote_memdump_response() -> RedirectResponse:
    return RedirectResponse(R2_TRUSTED_LINK, status_code=301)


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

    filename = _vault_filename(download)
    if filename == MEMDUMP_FILENAME:
        return _remote_memdump_response()

    target = _download_path(filename)
    return FileResponse(
        target,
        media_type="application/octet-stream",
        filename=target.name,
    )
