from __future__ import annotations

from fastapi import Depends

from app.core.config import settings
from app.db.dependencies import get_db
from app.db.session import Database
from app.services.auth import require_session_user
from app.services.progress import ProgressService, get_progress_service

from .repository import SqlTangoRepository
from .service import SubmissionGate, TangoService

_submission_gate = SubmissionGate(capacity=2)

def build_tango_service(
    db: Database,
    progress_service: ProgressService,
) -> TangoService:
    return TangoService(
        repository=SqlTangoRepository(db),
        progress_gateway=progress_service,
        final_flag=settings.flag,
    )

def get_tango_service(
    db: Database = Depends(get_db),
    progress_service: ProgressService = Depends(get_progress_service),
) -> TangoService:
    return build_tango_service(db, progress_service)

def get_stage3_submission_gate() -> SubmissionGate:
    return _submission_gate

def get_current_user_id(
    user=Depends(require_session_user),
    progress_service: ProgressService = Depends(get_progress_service),
) -> int:
    progress_service.require_stage3_access(user.user_id)
    return user.user_id
