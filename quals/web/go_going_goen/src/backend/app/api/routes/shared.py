from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.db.session import Database
from app.models.progress import EMPTY_PROGRESS
from app.services.auth import get_optional_session_user, require_session_user
from app.services.downloads import DownloadService, get_download_service
from app.services.progress import ProgressService, get_progress_service
from app.stages.stage1.dependencies import get_pinpoint_service
from app.stages.stage2.dependencies import get_queens_service
from app.stages.stage3.dependencies import get_tango_service

router = APIRouter()


@router.get("/me")
def get_me(user=Depends(get_optional_session_user)) -> dict[str, int | str | None]:
    if user is None:
        return {"user_id": None, "username": None}
    return {"user_id": user.user_id, "username": user.username}


@router.get("/progress")
def get_progress(
    user=Depends(get_optional_session_user),
) -> dict[str, object]:
    if user is None:
        payload = EMPTY_PROGRESS.as_payload()
        payload["downloads"] = {
            "stage1": False,
            "stage2": False,
            "stage3": False,
        }
        return payload
    with Database(team_id=user.team_id) as db:
        return ProgressService(db).get_progress(user.user_id)


@router.post("/reset")
def reset_all(
    user=Depends(require_session_user),
    pinpoint_service=Depends(get_pinpoint_service),
    queens_service=Depends(get_queens_service),
    tango_service=Depends(get_tango_service),
) -> dict[str, bool]:
    pinpoint_service.reset(user.user_id)
    queens_service.reset(user.user_id)
    tango_service.reset(user.user_id)
    return {"ok": True}


@router.get("/downloads")
def get_downloads(
    user=Depends(get_optional_session_user),
    download_service: DownloadService = Depends(get_download_service),
) -> dict[str, object]:
    if user is None:
        progress = EMPTY_PROGRESS.as_payload()
        progress["downloads"] = {
            "stage1": False,
            "stage2": False,
            "stage3": False,
        }
    else:
        with Database(team_id=user.team_id) as db:
            progress = ProgressService(db).get_progress(user.user_id)
    return {"downloads": download_service.list_downloads(progress)}


@router.get("/downloads/{stage_key}")
def download_stage_source(
    stage_key: str,
    user=Depends(require_session_user),
    progress_service: ProgressService = Depends(get_progress_service),
    download_service: DownloadService = Depends(get_download_service),
) -> FileResponse:
    progress = progress_service.get_progress(user.user_id)
    archive_path = download_service.build_archive(stage_key, progress)
    filename = archive_path.name
    return FileResponse(str(archive_path), media_type="application/gzip", filename=filename)
