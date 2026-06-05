from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

def configure_spa(app: FastAPI, directory: Path) -> None:
    if not directory.is_dir():
        return

    static_root = directory.resolve()
    assets_dir = static_root / "assets"
    index_path = static_root / "index.html"

    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    for filename in ("favicon.ico", "vite.svg"):
        asset_path = static_root / filename
        if asset_path.is_file():
            app.add_api_route(
                f"/{filename}",
                _build_file_handler(asset_path),
                methods=["GET"],
                include_in_schema=False,
            )

    if not index_path.is_file():
        return

    app.add_api_route(
        "/",
        _build_file_handler(index_path),
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route(
        "/{full_path:path}",
        _build_spa_handler(static_root, index_path),
        methods=["GET"],
        include_in_schema=False,
    )

def _build_file_handler(path: Path):
    async def serve_file() -> FileResponse:
        return FileResponse(path)

    return serve_file

def _build_spa_handler(static_root: Path, index_path: Path):
    async def serve_spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/") or full_path in {"healthz", "metrics"}:
            raise HTTPException(status_code=404)

        candidate = (static_root / full_path).resolve()
        try:
            candidate.relative_to(static_root)
        except ValueError as exc:
            raise HTTPException(status_code=404) from exc

        if candidate.is_file():
            return FileResponse(candidate)

        return FileResponse(index_path)

    return serve_spa
