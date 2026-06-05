from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.core.config import settings
from app.db.dependencies import get_db
from app.db.session import Database
from app.services.auth import require_session_user
from app.services.instance import InstanceService
from app.services.progress import ProgressService, get_progress_service

from .constants import GUESS_GATE_CAPACITY, RESET_COOLDOWN_SECONDS
from .repository import SqlPinpointRepository
from .service import PinpointService, GuessGate, ResetGate
from .wordbank import WordBank

_guess_gate = GuessGate(capacity=GUESS_GATE_CAPACITY)
_reset_gate = ResetGate(cooldown_seconds=RESET_COOLDOWN_SECONDS)

def build_pinpoint_service(
    db: Database,
    progress_service: ProgressService,
    instance_service: InstanceService,
) -> PinpointService:
    instance_seed = instance_service.ensure_seed()
    return PinpointService(
        repository=SqlPinpointRepository(db),
        progress_gateway=progress_service,
        wordbank=WordBank(
            _read_wordbank(),
            secret=settings.pinpoint_token,
            minimum_size=1000,
            subset_size=100,
        ),
        instance_seed=instance_seed,
    )

def get_pinpoint_service(
    db: Annotated[Database, Depends(get_db)],
    progress_service: Annotated[ProgressService, Depends(get_progress_service)],
) -> PinpointService:
    return build_pinpoint_service(db, progress_service, InstanceService(db))

def get_current_user_id(user=Depends(require_session_user)) -> int:
    return user.user_id

def get_stage1_guess_gate() -> GuessGate:
    return _guess_gate

def get_stage1_reset_gate() -> ResetGate:
    return _reset_gate

def _read_wordbank() -> list[str]:
    with open("app/stages/stage1/wordlist.txt") as f:
        return [line.strip() for line in f if line.strip()]
