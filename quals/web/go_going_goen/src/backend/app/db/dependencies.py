from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.db.session import Database
from app.models.auth import SessionUser
from app.services.auth import require_session_user


def get_db(user: Annotated[SessionUser, Depends(require_session_user)]):
    with Database(team_id=user.team_id) as db:
        yield db
