from __future__ import annotations

import pytest

from app.core.exceptions import AppError
from app.services.progress import ProgressService


class StubDatabase:
    def __init__(self, row: dict[str, object] | None) -> None:
        self.row = row

    def fetch_one(self, _query: str, _params: list[object]) -> dict[str, object] | None:
        return self.row


def test_require_stage2_access_rejects_users_without_stage1_clear() -> None:
    service = ProgressService(StubDatabase(row=None))  # type: ignore[arg-type]

    with pytest.raises(AppError) as exc_info:
        service.require_stage2_access(7)

    assert exc_info.value.status_code == 403
    assert exc_info.value.error == "stage_locked"
    assert exc_info.value.message == "Stage 2 is locked until Stage 1 is cleared."


def test_require_stage2_access_allows_users_with_stage1_clear() -> None:
    service = ProgressService(
        StubDatabase(
            row={
                "stage1_cleared": True,
                "stage2_cleared": False,
                "stage3_cleared": False,
            }
        )
    )  # type: ignore[arg-type]

    service.require_stage2_access(7)


def test_require_stage3_access_rejects_users_without_stage2_clear() -> None:
    service = ProgressService(
        StubDatabase(
            row={
                "stage1_cleared": True,
                "stage2_cleared": False,
                "stage3_cleared": False,
            }
        )
    )  # type: ignore[arg-type]

    with pytest.raises(AppError) as exc_info:
        service.require_stage3_access(9)

    assert exc_info.value.status_code == 403
    assert exc_info.value.error == "stage_locked"
    assert exc_info.value.message == "Stage 3 is locked until Stage 2 is cleared."


def test_require_stage3_access_allows_users_with_stage2_clear() -> None:
    service = ProgressService(
        StubDatabase(
            row={
                "stage1_cleared": True,
                "stage2_cleared": True,
                "stage3_cleared": False,
            }
        )
    )  # type: ignore[arg-type]

    service.require_stage3_access(9)
