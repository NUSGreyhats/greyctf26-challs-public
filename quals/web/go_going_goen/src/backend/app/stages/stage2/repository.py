from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
from typing import Protocol

from app.db.session import Database

from .constants import BOARD_SIZE
from .models import QueenPosition, SubmissionState


class ValidationSession(Protocol):
    def count_in_column(self, column: int) -> int: ...

    def count_in_row(self, row: int) -> int: ...

    def record_validation_step(
        self, *, step_kind: str, step_index: int, observed_count: int
    ) -> None: ...

    def count_total(self) -> int: ...


class BoardStore(Protocol):
    def list_queens(self, user_id: int) -> list[QueenPosition]: ...

    def count_total(self, user_id: int) -> int: ...

    def insert_queen(self, user_id: int, row: int, col: int) -> None: ...

    def insert_queens(self, user_id: int, queens: Iterable[QueenPosition]) -> None: ...

    def remove_queen(self, user_id: int, row: int, col: int) -> bool: ...

    def replace_board(self, user_id: int, queens: Iterable[QueenPosition]) -> None: ...

    def clear_validation_audit(self, user_id: int) -> None: ...

    def validation_session(
        self, user_id: int
    ) -> AbstractContextManager[ValidationSession]: ...


class SubmissionStore(Protocol):
    def get_submission(self, user_id: int) -> SubmissionState: ...

    def set_submission(
        self,
        user_id: int,
        *,
        status: str,
        progress_pct: int,
        last_result: str | None,
        last_submitted_at: datetime | None,
    ) -> SubmissionState: ...


class ProgressStore(Protocol):
    def unlock_stage3(self, user_id: int) -> None: ...


class SqlQueensBoardStore:
    def __init__(
        self,
        db: Database,
        *,
        db_factory: Callable[[], Database] = Database,
    ) -> None:
        self._db = db
        self._db_factory = db_factory

    def list_queens(self, user_id: int) -> list[QueenPosition]:
        rows = self._db.fetch_all(
            """
            SELECT row_idx, col_idx
            FROM queens_positions
            WHERE user_id = %s
            ORDER BY row_idx ASC, col_idx ASC, id ASC
            """,
            [user_id],
        )
        return [_queen_from_row(row) for row in rows]

    def count_total(self, user_id: int) -> int:
        total = self._db.fetch_val(
            "SELECT count(*) FROM queens_positions WHERE user_id = %s",
            [user_id],
        )
        return int(total or 0)

    def insert_queen(self, user_id: int, row: int, col: int) -> None:
        self._db.execute(
            """
            INSERT INTO queens_positions (user_id, row_idx, col_idx)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, row_idx, col_idx) DO NOTHING
            """,
            [user_id, row, col],
        )

    def insert_queens(self, user_id: int, queens: Iterable[QueenPosition]) -> None:
        pending = list(queens)
        if not pending:
            return
        values_sql = ", ".join(["(%s, %s, %s)"] * len(pending))
        params: list[int] = []
        for queen in pending:
            params.extend([user_id, queen.row, queen.col])
        self._db.execute(
            f"""
            INSERT INTO queens_positions (user_id, row_idx, col_idx)
            VALUES {values_sql}
            ON CONFLICT (user_id, row_idx, col_idx) DO NOTHING
            """,
            params,
        )

    def remove_queen(self, user_id: int, row: int, col: int) -> bool:
        removed = self._db.execute(
            """
            DELETE FROM queens_positions
            WHERE user_id = %s AND row_idx = %s AND col_idx = %s
            RETURNING id
            """,
            [user_id, row, col],
        )
        return removed is not None

    def replace_board(self, user_id: int, queens: Iterable[QueenPosition]) -> None:
        self._db.execute("DELETE FROM queens_positions WHERE user_id = %s", [user_id])
        for queen in queens:
            self.insert_queen(user_id, queen.row, queen.col)
        self.clear_validation_audit(user_id)

    def clear_validation_audit(self, user_id: int) -> None:
        self._db.execute(
            "DELETE FROM queens_validation_audit WHERE user_id = %s", [user_id]
        )

    @contextmanager
    def validation_session(self, user_id: int):
        with self._db_factory() as db:
            yield SqlQueensValidationSession(db, user_id)


class SqlQueensValidationSession:
    def __init__(self, db: Database, user_id: int) -> None:
        self._db = db
        self._user_id = user_id

    def count_in_column(self, column: int) -> int:
        total = self._db.fetch_val(
            """
            SELECT count(*)
            FROM queens_positions
            WHERE user_id = %s AND col_idx = %s
            """,
            [self._user_id, column],
        )
        return int(total or 0)

    def count_in_row(self, row: int) -> int:
        total = self._db.fetch_val(
            """
            SELECT count(*)
            FROM queens_positions
            WHERE user_id = %s AND row_idx = %s
            """,
            [self._user_id, row],
        )
        return int(total or 0)

    def record_validation_step(
        self, *, step_kind: str, step_index: int, observed_count: int
    ) -> None:
        checked_prefix_limit = step_index if step_kind == "row" else step_index + 1
        checked_prefix_occupied = int(
            self._db.fetch_val(
                """
                SELECT count(*)
                FROM queens_positions
                WHERE user_id = %s
                  AND row_idx < %s
                  AND col_idx < %s
                """,
                [self._user_id, checked_prefix_limit, checked_prefix_limit],
            )
            or 0
        )
        self._db.execute(
            """
            INSERT INTO queens_validation_audit (
                user_id,
                step_kind,
                step_index,
                observed_count,
                checked_prefix_limit,
                checked_prefix_occupied,
                board_snapshot
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                COALESCE(
                    (
                        SELECT jsonb_agg(
                            jsonb_build_object(
                                'r', row_idx,
                                'c', col_idx,
                                'verified_at', extract(epoch from now())
                            )
                        )
                        FROM queens_positions
                        WHERE user_id = %s
                    ),
                    '[]'::jsonb
                )
            )
            """,
            [
                self._user_id,
                step_kind,
                step_index,
                observed_count,
                checked_prefix_limit,
                checked_prefix_occupied,
                self._user_id,
            ],
        )

    def count_total(self) -> int:
        total = self._db.fetch_val(
            "SELECT count(*) FROM queens_positions WHERE user_id = %s",
            [self._user_id],
        )
        return int(total or 0)


class SqlQueensSubmissionStore:
    def __init__(self, *, db_factory: Callable[[], Database] = Database) -> None:
        self._db_factory = db_factory

    def get_submission(self, user_id: int) -> SubmissionState:
        with self._db_factory() as db:
            return self._get_submission(db, user_id)

    def set_submission(
        self,
        user_id: int,
        *,
        status: str,
        progress_pct: int,
        last_result: str | None,
        last_submitted_at: datetime | None,
    ) -> SubmissionState:
        with self._db_factory() as db:
            row = db.execute(
                """
                INSERT INTO queens_submissions (
                    user_id,
                    status,
                    progress_pct,
                    last_result,
                    last_submitted_at,
                    updated_at
                ) VALUES (%s, %s, %s, %s, %s, now())
                ON CONFLICT (user_id) DO UPDATE
                SET status = EXCLUDED.status,
                    progress_pct = EXCLUDED.progress_pct,
                    last_result = EXCLUDED.last_result,
                    last_submitted_at = EXCLUDED.last_submitted_at,
                    updated_at = now()
                RETURNING status, progress_pct, last_result, last_submitted_at
                """,
                [user_id, status, progress_pct, last_result, last_submitted_at],
            )
            if row is None:
                raise LookupError(
                    f"Missing queens submission row for user_id={user_id}"
                )
            return _submission_from_row(row)

    def _get_submission(self, db: Database, user_id: int) -> SubmissionState:
        db.execute(
            """
            INSERT INTO queens_submissions (user_id)
            VALUES (%s)
            ON CONFLICT (user_id) DO NOTHING
            """,
            [user_id],
        )
        row = db.fetch_one(
            """
            SELECT status, progress_pct, last_result, last_submitted_at
            FROM queens_submissions
            WHERE user_id = %s
            """,
            [user_id],
        )
        if row is None:
            raise LookupError(f"Missing queens submission row for user_id={user_id}")
        return _submission_from_row(row)


def _queen_from_row(row: dict[str, object]) -> QueenPosition:
    return QueenPosition(row=int(row["row_idx"]), col=int(row["col_idx"]))


def _submission_from_row(row: dict[str, object]) -> SubmissionState:
    return SubmissionState(
        status=str(row["status"]),
        progress_pct=int(row["progress_pct"]),
        last_result=row["last_result"] if row["last_result"] is not None else None,
        last_submitted_at=row["last_submitted_at"],
    )
