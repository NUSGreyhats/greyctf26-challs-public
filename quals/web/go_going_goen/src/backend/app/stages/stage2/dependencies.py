from __future__ import annotations

from fastapi import Depends

from app.db.dependencies import get_db
from app.db.session import Database
from app.models.auth import SessionUser
from app.services.auth import require_session_user
from app.services.progress import ProgressService, get_progress_service

from .constants import SUBMISSION_GATE_CAPACITY
from .repository import SqlQueensBoardStore, SqlQueensSubmissionStore
from .service import QueensService, SubmissionGate

_submission_gate = SubmissionGate(capacity=SUBMISSION_GATE_CAPACITY)

def get_current_user_id(
    user=Depends(require_session_user),
    progress_service: ProgressService = Depends(get_progress_service),
) -> int:
    progress_service.require_stage2_access(user.user_id)
    return user.user_id

def get_queens_service(
    db: Database = Depends(get_db),
    progress_service: ProgressService = Depends(get_progress_service),
    user: SessionUser = Depends(require_session_user),
) -> QueensService:
    def db_factory() -> Database:
        return Database(team_id=user.team_id)

    return QueensService(
        board_store=SqlQueensBoardStore(db, db_factory=db_factory),
        submission_store=SqlQueensSubmissionStore(db_factory=db_factory),
        progress_store=progress_service,
    )

def get_stage2_submission_gate() -> SubmissionGate:
    return _submission_gate
