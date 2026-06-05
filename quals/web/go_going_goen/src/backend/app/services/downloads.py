from __future__ import annotations

import tarfile
import tempfile
from pathlib import Path

from pathlib import Path

from fastapi import Depends

from app.core.exceptions import AppError
from app.db.dependencies import get_db
from app.db.session import Database

type DownloadManifestEntry = dict[str, str]

DOWNLOAD_MANIFESTS: dict[str, dict[str, object]] = {
    "stage1": {
        "filename": "stage1-source.tar.gz",
        "note": "Pinpoint backend implementation files.",
        "manifest": [
            {
                "source": "app/stages/stage1/wordlist.txt",
                "archive_name": "wordlist.txt",
            },
            {
                "source": "app/stages/stage1/router.py",
                "archive_name": "router.py",
            },
            {
                "source": "app/stages/stage1/constants.py",
                "archive_name": "constants.py",
            },
            {
                "source": "app/stages/stage1/service.py",
                "archive_name": "service.py",
            },
            {
                "source": "app/stages/stage1/models.py",
                "archive_name": "models.py",
            },
            {
                "source": "app/stages/stage1/wordbank.py",
                "archive_name": "wordbank.py",
            },
        ],
    },
    "stage2": {
        "filename": "stage2-source.tar.gz",
        "note": "Queens backend implementation files.",
        "manifest": [
            {
                "source": "app/stages/stage2/router.py",
                "archive_name": "router.py",
            },
            {
                "source": "app/stages/stage2/constants.py",
                "archive_name": "constants.py",
            },
            {
                "source": "app/stages/stage2/service.py",
                "archive_name": "service.py",
            },
            {
                "source": "app/stages/stage2/models.py",
                "archive_name": "models.py",
            },
            {
                "source": "app/stages/stage2/constants.py",
                "archive_name": "constants.py",
            },
        ],
    },
    "stage3": {
        "filename": "stage3-source.tar.gz",
        "note": "Tango backend implementation files.",
        "manifest": [
            {
                "source": "app/stages/stage3/router.py",
                "archive_name": "router.py",
            },
            {
                "source": "app/stages/stage3/service.py",
                "archive_name": "service.py",
            },
            {
                "source": "app/stages/stage3/models.py",
                "archive_name": "models.py",
            },
        ],
    },
}


class DownloadService:
    def list_downloads(self, progress: dict[str, object]) -> list[dict[str, object]]:
        gates = progress["downloads"]
        return [
            {
                "stage": stage,
                "unlocked": bool(gates[stage]),
                "filename": descriptor["filename"],
                "note": descriptor["note"],
                "ready": bool(descriptor["manifest"]),
            }
            for stage, descriptor in DOWNLOAD_MANIFESTS.items()
        ]

    def build_archive(self, stage: str, progress: dict[str, object]) -> Path:
        descriptor = DOWNLOAD_MANIFESTS.get(stage)
        if descriptor is None:
            raise AppError(
                status_code=404,
                error="download_not_found",
                message="Unknown download target.",
            )

        if not bool(progress["downloads"][stage]):
            raise AppError(
                status_code=403,
                error="download_locked",
                message="Source download is still locked.",
            )
        manifest = descriptor["manifest"]
        if not manifest:
            raise AppError(
                status_code=404,
                error="source_unavailable",
                message="Source bundle is not registered yet.",
            )

        temp_dir = Path(tempfile.mkdtemp(prefix=f"{stage}-source-"))
        archive_path = temp_dir / str(descriptor["filename"])
        repo_root = Database.project_root()
        with tarfile.open(archive_path, "w:gz") as archive:
            for relative_path in manifest:
                entry = relative_path
                source_path = (repo_root / str(entry["source"])).resolve()
                if not source_path.exists():
                    raise AppError(
                        status_code=404,
                        error="source_unavailable",
                        message=f"Registered source file is missing: {entry['source']}",
                    )
                archive.add(source_path, arcname=f"{stage}/{entry['archive_name']}")
        return archive_path


def get_download_service() -> DownloadService:
    return DownloadService()
