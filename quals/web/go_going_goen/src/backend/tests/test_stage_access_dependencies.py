from __future__ import annotations

import pytest

from app.core.exceptions import AppError
from app.models.auth import SessionUser
from app.stages.stage2.dependencies import (
    get_current_user_id as get_stage2_user_id,
    get_queens_service,
)
from app.stages.stage3.dependencies import get_current_user_id as get_stage3_user_id


class ProgressServiceStub:
    def __init__(self, stage2_error: AppError | None = None, stage3_error: AppError | None = None) -> None:
        self.stage2_error = stage2_error
        self.stage3_error = stage3_error
        self.stage2_calls: list[int] = []
        self.stage3_calls: list[int] = []

    def require_stage2_access(self, user_id: int) -> None:
        self.stage2_calls.append(user_id)
        if self.stage2_error is not None:
            raise self.stage2_error

    def require_stage3_access(self, user_id: int) -> None:
        self.stage3_calls.append(user_id)
        if self.stage3_error is not None:
            raise self.stage3_error


def test_stage2_dependency_checks_progress_before_returning_user_id() -> None:
    progress = ProgressServiceStub()
    user = SessionUser(user_id=41, username="player", team_id="team-a")

    user_id = get_stage2_user_id(user=user, progress_service=progress)

    assert user_id == 41
    assert progress.stage2_calls == [41]


def test_stage2_dependency_propagates_locked_error() -> None:
    progress = ProgressServiceStub(
        stage2_error=AppError(
            status_code=403,
            error="stage_locked",
            message="Stage 2 is locked until Stage 1 is cleared.",
        )
    )
    user = SessionUser(user_id=41, username="player", team_id="team-a")

    with pytest.raises(AppError) as exc_info:
        get_stage2_user_id(user=user, progress_service=progress)

    assert exc_info.value.message == "Stage 2 is locked until Stage 1 is cleared."
    assert progress.stage2_calls == [41]


def test_stage2_service_uses_team_scoped_factories_for_secondary_connections() -> None:
    progress = ProgressServiceStub()
    user = SessionUser(user_id=41, username="player", team_id="team-a")
    db = object()

    service = get_queens_service(
        db=db,  # type: ignore[arg-type]
        progress_service=progress,  # type: ignore[arg-type]
        user=user,
    )

    board_db = service._board_store._db_factory()
    submission_db = service._submission_store._db_factory()

    assert board_db._team_id == "team-a"
    assert submission_db._team_id == "team-a"


def test_stage3_dependency_checks_progress_before_returning_user_id() -> None:
    progress = ProgressServiceStub()
    user = SessionUser(user_id=52, username="player", team_id="team-a")

    user_id = get_stage3_user_id(user=user, progress_service=progress)

    assert user_id == 52
    assert progress.stage3_calls == [52]


def test_stage3_dependency_propagates_locked_error() -> None:
    progress = ProgressServiceStub(
        stage3_error=AppError(
            status_code=403,
            error="stage_locked",
            message="Stage 3 is locked until Stage 2 is cleared.",
        )
    )
    user = SessionUser(user_id=52, username="player", team_id="team-a")

    with pytest.raises(AppError) as exc_info:
        get_stage3_user_id(user=user, progress_service=progress)

    assert exc_info.value.message == "Stage 3 is locked until Stage 2 is cleared."
    assert progress.stage3_calls == [52]
