from __future__ import annotations

from fastapi import Depends

from app.core.exceptions import AppError
from app.db.dependencies import get_db
from app.db.session import Database
from app.models.auth import SessionUser
from app.models.progress import EMPTY_PROGRESS, ProgressState

class ProgressService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get_progress(self, user_id: int) -> dict[str, object]:
        return self._get_progress_state(user_id).as_payload()

    def _get_progress_state(self, user_id: int) -> ProgressState:
        row = self._db.fetch_one(
            """
            SELECT
                stage1_cleared,
                stage2_cleared,
                stage3_cleared
            FROM user_progress
            WHERE user_id = %s
            """,
            [user_id],
        )
        if row is None:
            return EMPTY_PROGRESS

        return ProgressState(
            stage1_cleared=bool(row["stage1_cleared"]),
            stage2_cleared=bool(row["stage2_cleared"]),
            stage3_cleared=bool(row["stage3_cleared"]),
        )

    def get_progress_for_optional_user(self, user: SessionUser | None) -> dict[str, object]:
        if user is None:
            payload = EMPTY_PROGRESS.as_payload()
            payload["downloads"] = {
                "stage1": False,
                "stage2": False,
                "stage3": False,
            }
            return payload
        return self.get_progress(user.user_id)

    def unlock_stage2(self, user_id: int) -> None:
        self._db.execute(
            """
            UPDATE user_progress
            SET stage1_cleared = TRUE,
                updated_at = now()
            WHERE user_id = %s
            """,
            [user_id],
        )

    def unlock_stage3(self, user_id: int) -> None:
        self._db.execute(
            """
            UPDATE user_progress
            SET stage2_cleared = TRUE,
                updated_at = now()
            WHERE user_id = %s
            """,
            [user_id],
        )

    def mark_stage3_cleared(self, user_id: int) -> None:
        self._db.execute(
            """
            UPDATE user_progress
            SET stage3_cleared = TRUE,
                updated_at = now()
            WHERE user_id = %s
            """,
            [user_id],
        )

    def is_stage3_cleared(self, user_id: int) -> bool:
        return self._get_progress_state(user_id).stage3_cleared

    def require_stage2_access(self, user_id: int) -> None:
        progress = self._get_progress_state(user_id)
        if not progress.stage1_cleared:
            raise AppError(
                status_code=403,
                error="stage_locked",
                message="Stage 2 is locked until Stage 1 is cleared.",
            )

    def require_stage3_access(self, user_id: int) -> None:
        progress = self._get_progress_state(user_id)
        if not progress.stage2_cleared:
            raise AppError(
                status_code=403,
                error="stage_locked",
                message="Stage 3 is locked until Stage 2 is cleared.",
            )

def get_progress_service(db: Database = Depends(get_db)) -> ProgressService:
    return ProgressService(db)
