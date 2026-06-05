from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.stages.stage2.constants import BOARD_SIZE, WIN_THRESHOLD
from app.stages.stage2.models import QueenPosition, SubmissionState
from app.stages.stage2.testing import (
    InMemoryBoardStore,
    InMemorySubmissionStore,
)
from app.stages.stage2.service import (
    InvalidBoardError,
    OutOfBoundsError,
    QueensService,
    default_board,
)


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class ProgressGatewayStub:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def unlock_stage3(self, user_id: int) -> None:
        self.calls.append(user_id)


def make_service(
    board_store: InMemoryBoardStore | None = None,
) -> tuple[
    QueensService, InMemoryBoardStore, InMemorySubmissionStore, ProgressGatewayStub
]:
    board = board_store or InMemoryBoardStore()
    submissions = InMemorySubmissionStore()
    progress = ProgressGatewayStub()
    service = QueensService(
        board_store=board,
        submission_store=submissions,
        progress_store=progress,
        clock=FixedClock(datetime(2026, 5, 12, tzinfo=UTC)),
    )
    return service, board, submissions, progress


def test_default_board_snapshot_starts_empty() -> None:
    service, _, _, _ = make_service()

    snapshot = service.get_board(user_id=7)

    assert snapshot.size == BOARD_SIZE
    assert snapshot.total_queens == 0
    assert snapshot.queens == []
    assert snapshot.submission.status == "idle"


def test_add_and_remove_queen_return_updated_total() -> None:
    service, _, _, _ = make_service()

    total_after_add = service.add_queen(user_id=1, row=0, col=1)
    total_after_remove = service.remove_queen(user_id=1, row=0, col=1)

    assert total_after_add == 1
    assert total_after_remove == 0


def test_add_is_idempotent_for_occupied_square() -> None:
    service, _, _, _ = make_service()

    first_total = service.add_queen(user_id=1, row=0, col=1)
    second_total = service.add_queen(user_id=1, row=0, col=1)

    assert first_total == 1
    assert second_total == 1


def test_add_rejects_out_of_bounds_positions() -> None:
    service, _, _, _ = make_service()

    with pytest.raises(OutOfBoundsError):
        service.add_queen(user_id=1, row=50, col=0)


def test_submit_marks_valid_board_complete_without_unlock() -> None:
    service, _, submissions, progress = make_service()

    result = service.submit(user_id=2)
    state = submissions.get_submission(2)

    assert result.result == "valid"
    assert result.total_queens == 0
    assert state.status == "valid"
    assert state.progress_pct == 100
    assert state.last_result == "valid"
    assert progress.calls == []


def test_submit_fails_when_a_row_or_column_has_multiple_queens() -> None:
    service, board, submissions, progress = make_service()
    board.insert_queen(user_id=3, row=0, col=0)
    board.insert_queen(user_id=3, row=0, col=1)

    with pytest.raises(InvalidBoardError):
        service.submit(user_id=3)

    state = submissions.get_submission(3)
    assert state.status == "failed"
    assert state.last_result == "invalid"
    assert progress.calls == []


def test_reset_restores_empty_board_and_idle_submission() -> None:
    service, _, submissions, _ = make_service()
    service.add_queen(user_id=5, row=0, col=1)
    submissions.set_submission(
        5,
        status="won",
        progress_pct=100,
        last_result="win",
        last_submitted_at=datetime(2026, 5, 12, tzinfo=UTC),
    )

    snapshot = service.reset(user_id=5)

    assert snapshot.total_queens == 0
    assert snapshot.queens == default_board()
    assert snapshot.submission == SubmissionState(
        status="idle",
        progress_pct=0,
        last_result=None,
        last_submitted_at=None,
    )
