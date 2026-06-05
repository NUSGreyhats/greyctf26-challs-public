from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Protocol

from app.observability.metrics import get_metrics

from .constants import BOARD_SIZE, SUBMISSION_GATE_CAPACITY, WIN_THRESHOLD
from .models import BoardSnapshot, QueenPosition, SubmitResult
from .repository import BoardStore, ProgressStore, SubmissionStore


class OutOfBoundsError(ValueError):
    pass


class InvalidBoardError(RuntimeError):
    pass


class TooManySubmissionsError(RuntimeError):
    def __init__(self, message: str = "Too many submissions.") -> None:
        super().__init__(message)


class SubmissionGate:
    def __init__(self, *, capacity: int = SUBMISSION_GATE_CAPACITY) -> None:
        self._capacity = capacity
        self._semaphores: dict[int, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(capacity)
        )

    @asynccontextmanager
    async def acquire(self, user_id: int, timeout: float = 0.25):
        semaphore = self._semaphores[user_id]
        started = time.perf_counter()
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            get_metrics().observe_gate_wait(
                stage="stage2",
                outcome="timeout",
                duration_seconds=time.perf_counter() - started,
            )
            raise TooManySubmissionsError() from exc
        get_metrics().observe_gate_wait(
            stage="stage2",
            outcome="acquired",
            duration_seconds=time.perf_counter() - started,
        )

        try:
            yield
        finally:
            semaphore.release()

    @property
    def capacity(self) -> int:
        return self._capacity


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def default_board() -> list[QueenPosition]:
    return []


class QueensService:
    def __init__(
        self,
        *,
        board_store: BoardStore,
        submission_store: SubmissionStore,
        progress_store: ProgressStore,
        clock: Clock | None = None,
    ) -> None:
        self._board_store = board_store
        self._submission_store = submission_store
        self._progress_store = progress_store
        self._clock = clock or SystemClock()

    def get_board(self, user_id: int) -> BoardSnapshot:
        self._ensure_default_board(user_id)
        queens = self._board_store.list_queens(user_id)
        submission = self._submission_store.get_submission(user_id)
        return BoardSnapshot(
            size=BOARD_SIZE,
            queens=queens,
            total_queens=len(queens),
            submission=submission,
        )

    def add_queen(self, user_id: int, row: int, col: int) -> int:
        self._validate_bounds(row, col)
        self._ensure_default_board(user_id)
        self._board_store.insert_queen(user_id, row, col)
        return self._board_store.count_total(user_id)

    def add_queens(self, user_id: int, queens: list[QueenPosition]) -> int:
        for queen in queens:
            self._validate_bounds(queen.row, queen.col)
        self._ensure_default_board(user_id)
        self._board_store.insert_queens(user_id, queens)
        return self._board_store.count_total(user_id)

    def remove_queen(self, user_id: int, row: int, col: int) -> int:
        self._validate_bounds(row, col)
        self._ensure_default_board(user_id)
        self._board_store.remove_queen(user_id, row, col)
        return self._board_store.count_total(user_id)

    def reset(self, user_id: int) -> BoardSnapshot:
        self._board_store.replace_board(user_id, default_board())
        submission = self._submission_store.set_submission(
            user_id,
            status="idle",
            progress_pct=0,
            last_result=None,
            last_submitted_at=None,
        )
        return BoardSnapshot(
            size=BOARD_SIZE,
            queens=self._board_store.list_queens(user_id),
            total_queens=self._board_store.count_total(user_id),
            submission=submission,
        )

    def submit(self, user_id: int) -> SubmitResult:
        started = time.perf_counter()
        outcome = "unknown"
        try:
            self._ensure_default_board(user_id)
            submitted_at = self._clock.now()
            self._set_submission_state(
                user_id,
                status="validating",
                progress_pct=0,
                last_result="pending",
                last_submitted_at=submitted_at,
            )

            # runs in a single transaction to ensure a consistent view of the board state during validation
            with self._board_store.validation_session(user_id) as validation:
                for index in range(BOARD_SIZE):
                    row_count = validation.count_in_row(index)
                    validation.record_validation_step(
                        step_kind="row",
                        step_index=index,
                        observed_count=row_count,
                    )
                    if row_count > 1:
                        outcome = "invalid"
                        self._fail_submission(user_id, submitted_at)
                        raise InvalidBoardError("Board failed validation.")

                    column_count = validation.count_in_column(index)
                    validation.record_validation_step(
                        step_kind="column",
                        step_index=index,
                        observed_count=column_count,
                    )
                    if column_count > 1:
                        outcome = "invalid"
                        self._fail_submission(user_id, submitted_at)
                        raise InvalidBoardError("Board failed validation.")

                total = validation.count_total()

            if total >= WIN_THRESHOLD:
                outcome = "win"
                self._progress_store.unlock_stage3(user_id)
                self._set_submission_state(
                    user_id,
                    status="won",
                    progress_pct=100,
                    last_result="win",
                    last_submitted_at=submitted_at,
                )
                return SubmitResult(result="win", total_queens=total)

            outcome = "valid"
            self._set_submission_state(
                user_id,
                status="valid",
                progress_pct=100,
                last_result="valid",
                last_submitted_at=submitted_at,
            )
            return SubmitResult(result="valid", total_queens=total)
        finally:
            get_metrics().observe_stage_submit(
                stage="stage2",
                outcome=outcome,
                duration_seconds=time.perf_counter() - started,
            )

    def _ensure_default_board(self, user_id: int) -> None:
        if self._board_store.count_total(user_id) == 0:
            self._board_store.replace_board(user_id, default_board())

    def _fail_submission(self, user_id: int, submitted_at: datetime) -> None:
        self._set_submission_state(
            user_id,
            status="failed",
            progress_pct=100,
            last_result="invalid",
            last_submitted_at=submitted_at,
        )

    def _set_submission_state(
        self,
        user_id: int,
        *,
        status: str,
        progress_pct: int,
        last_result: str | None,
        last_submitted_at: datetime | None,
    ) -> None:
        self._submission_store.set_submission(
            user_id,
            status=status,
            progress_pct=progress_pct,
            last_result=last_result,
            last_submitted_at=last_submitted_at,
        )

    @staticmethod
    def _validate_bounds(row: int, col: int) -> None:
        if not 0 <= row < BOARD_SIZE or not 0 <= col < BOARD_SIZE:
            raise OutOfBoundsError("Queen position is outside the board.")
