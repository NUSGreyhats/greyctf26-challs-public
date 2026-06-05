from pathlib import Path
import tarfile

import pytest

from app.services.downloads import DOWNLOAD_MANIFESTS, DownloadService


@pytest.mark.parametrize("stage", sorted(DOWNLOAD_MANIFESTS))
def test_download_manifest_paths_resolve_from_backend_project_root(stage: str) -> None:
    progress = {
        "downloads": {
            "stage1": True,
            "stage2": True,
            "stage3": True,
        }
    }

    service = DownloadService()
    archive_path = service.build_archive(stage, progress)

    assert archive_path.exists()
    assert archive_path.name == DOWNLOAD_MANIFESTS[stage]["filename"]
    assert Path(archive_path).suffixes == [".tar", ".gz"]
    with tarfile.open(archive_path, "r:gz") as archive:
        names = sorted(archive.getnames())

    expected = sorted(
        f"{stage}/{entry['archive_name']}"
        for entry in DOWNLOAD_MANIFESTS[stage]["manifest"]
    )
    assert names == expected
