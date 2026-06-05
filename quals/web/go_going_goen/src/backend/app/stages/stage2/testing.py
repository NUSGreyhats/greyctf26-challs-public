from __future__ import annotations

from collections.abc import Iterable
from contextlib import contextmanager
from datetime import datetime

from .models import QueenPosition, SubmissionState

class InMemoryBoardStore:
    def __init__(self) -> None:
        self._boards: dict[int, list[QueenPosition]] = {}

    def list_queens(self, user_id: int) -> list[QueenPosition]:
        return list(self._boards.get(user_id, []))

    def count_total(self, user_id: int) -> int:
        return len(self._boards.get(user_id, []))

    def insert_queen(self, user_id: int, row: int, col: int) -> None:
        board = self._boards.setdefault(user_id, [])
        if not any(queen.row == row and queen.col == col for queen in board):
            board.append(QueenPosition(row=row, col=col))

    def insert_queens(self, user_id: int, queens: Iterable[QueenPosition]) -> None:
        for queen in queens:
            self.insert_queen(user_id, queen.row, queen.col)

    def remove_queen(self, user_id: int, row: int, col: int) -> bool:
        board = self._boards.setdefault(user_id, [])
        for index, queen in enumerate(board):
            if queen.row == row and queen.col == col:
                del board[index]
                return True
        return False

    def replace_board(self, user_id: int, queens: Iterable[QueenPosition]) -> None:
        self._boards[user_id] = list(queens)

    def clear_validation_audit(self, user_id: int) -> None:
        return None

    @contextmanager
    def validation_session(self, user_id: int):
        yield InMemoryValidationSession(self, user_id)

class InMemoryValidationSession:
    def __init__(self, board_store: InMemoryBoardStore, user_id: int) -> None:
        self._board_store = board_store
        self._user_id = user_id

    def count_in_column(self, column: int) -> int:
        return sum(
            1
            for queen in self._board_store.list_queens(self._user_id)
            if queen.col == column
        )

    def count_in_row(self, row: int) -> int:
        return sum(
            1
            for queen in self._board_store.list_queens(self._user_id)
            if queen.row == row
        )

    def record_validation_step(
        self, *, step_kind: str, step_index: int, observed_count: int
    ) -> None:
        return None

    def count_total(self) -> int:
        return self._board_store.count_total(self._user_id)

class InMemorySubmissionStore:
    def __init__(self) -> None:
        self._submissions: dict[int, SubmissionState] = {}

    def get_submission(self, user_id: int) -> SubmissionState:
        return self._submissions.setdefault(
            user_id,
            SubmissionState(
                status="idle",
                progress_pct=0,
                last_result=None,
                last_submitted_at=None,
            ),
        )

    def set_submission(
        self,
        user_id: int,
        *,
        status: str,
        progress_pct: int,
        last_result: str | None,
        last_submitted_at: datetime | None,
    ) -> SubmissionState:
        state = SubmissionState(
            status=status,
            progress_pct=progress_pct,
            last_result=last_result,
            last_submitted_at=last_submitted_at,
        )
        self._submissions[user_id] = state
        return state
