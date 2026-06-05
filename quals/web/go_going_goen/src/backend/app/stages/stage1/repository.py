from __future__ import annotations

from typing import Any, Protocol

from .models import PinpointUserState

class DatabaseSession(Protocol):
    def fetch_one(self, query: str, params: list[Any]) -> dict[str, Any] | None: ...

    def fetch_all(self, query: str, params: list[Any]) -> list[dict[str, Any]]: ...

    def execute(self, query: str, params: list[Any]) -> dict[str, Any] | None: ...

class PinpointProgressGateway(Protocol):
    def unlock_stage2(self, user_id: int) -> None: ...

class PinpointRepository(Protocol):
    def fetch_user_state(self, user_id: int) -> PinpointUserState | None: ...

    def create_user_state(self, state: PinpointUserState) -> None: ...

    def fetch_recent_guesses(self, user_id: int, limit: int = 5) -> list[str]: ...

    def apply_guess(
        self, *, user_id: int, is_correct: bool, guess: str
    ) -> PinpointUserState: ...

    def reset_user_state(
        self, user_id: int, *, puzzle_answer: str
    ) -> PinpointUserState: ...

class SqlPinpointRepository:
    def __init__(self, db: DatabaseSession) -> None:
        self._db = db

    def fetch_user_state(self, user_id: int) -> PinpointUserState | None:
        row = self._db.fetch_one(
            """
            SELECT user_id, guesses_used, solved, puzzle_answer, last_result
            FROM pinpoint_users
            WHERE user_id = %s
            """,
            [user_id],
        )
        return _state_from_row(row) if row else None

    def create_user_state(self, state: PinpointUserState) -> None:
        self._db.execute(
            """
            INSERT INTO pinpoint_users (
                user_id,
                guesses_used,
                solved,
                puzzle_answer,
                last_result
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            [
                state.user_id,
                state.guesses_used,
                state.solved,
                state.puzzle_answer,
                state.last_result,
            ],
        )

    def fetch_recent_guesses(self, user_id: int, limit: int = 5) -> list[str]:
        rows = self._db.fetch_all(
            """
            SELECT guess
            FROM pinpoint_guess_log
            WHERE user_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            [user_id, limit],
        )
        return [str(row["guess"]) for row in rows]

    def apply_guess(
        self, *, user_id: int, is_correct: bool, guess: str
    ) -> PinpointUserState:
        result_label = "correct" if is_correct else "wrong"
        row = self._db.execute(
            """
            UPDATE pinpoint_users
            SET guesses_used = guesses_used + 1,
                solved = solved OR %s,
                last_result = %s
            WHERE user_id = %s
            RETURNING user_id, guesses_used, solved, puzzle_answer, last_result
            """,
            [is_correct, result_label, user_id],
        )
        self._db.execute(
            """
            INSERT INTO pinpoint_guess_log (user_id, guess, accepted, was_correct)
            VALUES (%s, %s, TRUE, %s)
            """,
            [user_id, guess, is_correct],
        )
        if row is None:
            raise LookupError(f"Missing pinpoint user row for user_id={user_id}")
        return _state_from_row(row)

    def reset_user_state(
        self, user_id: int, *, puzzle_answer: str
    ) -> PinpointUserState:
        self._db.execute(
            """
            DELETE FROM pinpoint_guess_log
            WHERE user_id = %s
            """,
            [user_id],
        )
        row = self._db.execute(
            """
            UPDATE pinpoint_users
            SET guesses_used = 0,
                solved = FALSE,
                last_result = NULL,
                puzzle_answer = %s
            WHERE user_id = %s
            RETURNING user_id, guesses_used, solved, puzzle_answer, last_result
            """,
            [puzzle_answer, user_id],
        )
        if row is None:
            raise LookupError(f"Missing pinpoint user row for user_id={user_id}")
        return _state_from_row(row)

def _state_from_row(row: dict[str, Any]) -> PinpointUserState:
    return PinpointUserState(
        user_id=int(row["user_id"]),
        guesses_used=int(row["guesses_used"]),
        solved=bool(row["solved"]),
        puzzle_answer=str(row["puzzle_answer"]),
        last_result=row["last_result"],
    )
