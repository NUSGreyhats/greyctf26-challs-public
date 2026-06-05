from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, Query

from app.core.config import settings
from app.core.exceptions import AppError
from app.db.session import Database

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin_token(
    authorization: str | None = Header(default=None),
    admin_token: str | None = Query(default=None),
) -> None:
    if not settings.admin_token:
        raise AppError(
            status_code=503,
            error="admin_disabled",
            message="Admin access is not configured.",
        )

    provided: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization.split(" ", 1)[1].strip()
    elif admin_token:
        provided = admin_token

    if not provided or not hmac.compare_digest(provided, settings.admin_token):
        raise AppError(
            status_code=401,
            error="unauthorized",
            message="Admin authentication required.",
        )


@router.get("/health-detail")
def health_detail(_admin: None = Depends(require_admin_token)) -> dict[str, object]:
    with Database.bootstrap() as db:
        session_count = db.fetch_val("SELECT COUNT(*) FROM auth_sessions", [])
        active_sessions = db.fetch_val(
            "SELECT COUNT(*) FROM auth_sessions WHERE expires_at > now()",
            [],
        )

    return {
        "ok": True,
        "database_endpoint": settings.database_endpoint,
        "session_count": int(session_count or 0),
        "active_session_count": int(active_sessions or 0),
    }


@router.post("/reset-all")
def reset_all_mutable_state(_admin: None = Depends(require_admin_token)) -> dict[str, bool]:
    with Database.bootstrap() as db:
        db.execute("SELECT admin_reset_all_mutable_state()", [])
    return {"ok": True}
