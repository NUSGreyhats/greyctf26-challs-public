from __future__ import annotations

import time
from collections import defaultdict

from fastapi import APIRouter, Header, Query, Response
from pydantic import BaseModel, Field

from app.core.exceptions import AppError
from app.services.auth import (
    clear_session_cookie,
    create_session_from_token,
    set_session_cookie,
)
from app.services.ctfd_token import is_plausible_team_token

router = APIRouter(prefix="/auth", tags=["auth"])

_rate_limit_by_ip: dict[str, list[float]] = defaultdict(list)
_rate_limit_by_token: dict[str, list[float]] = defaultdict(list)


class SessionBootstrapRequest(BaseModel):
    token: str = Field(min_length=8)


def _enforce_rate_limit(
    *,
    ip: str,
    token: str,
    ip_limit: int = 30,
    token_limit: int = 10,
    window_seconds: int = 60,
) -> None:
    now = time.time()
    cutoff = now - window_seconds

    ip_hits = [stamp for stamp in _rate_limit_by_ip[ip] if stamp >= cutoff]
    token_hits = [stamp for stamp in _rate_limit_by_token[token] if stamp >= cutoff]
    if len(ip_hits) >= ip_limit or len(token_hits) >= token_limit:
        raise AppError(
            status_code=429,
            error="rate_limited",
            message="Too many authentication attempts.",
        )

    ip_hits.append(now)
    token_hits.append(now)
    _rate_limit_by_ip[ip] = ip_hits
    _rate_limit_by_token[token] = token_hits


def _bootstrap_session(token: str, response: Response) -> dict[str, bool]:
    if not is_plausible_team_token(token):
        raise AppError(
            status_code=401,
            error="invalid_token",
            message="Authentication failed.",
        )

    _user, session_id = create_session_from_token(token)
    set_session_cookie(response, session_id)
    return {"ok": True, "authenticated": True}


def _client_ip(x_forwarded_for: str | None) -> str:
    return (x_forwarded_for or "local").split(",")[0].strip()


@router.post("/session")
def post_session(
    response: Response,
    body: SessionBootstrapRequest | None = None,
    token: str | None = Query(default=None, min_length=8),
    x_forwarded_for: str | None = Header(default=None),
) -> dict[str, bool]:
    resolved_token = body.token if body is not None else token
    if resolved_token is None:
        raise AppError(
            status_code=400,
            error="invalid_request",
            message="Authentication failed.",
        )

    client_ip = _client_ip(x_forwarded_for)
    _enforce_rate_limit(ip=client_ip, token=resolved_token)
    return _bootstrap_session(resolved_token, response)


@router.get("/session")
def get_session(
    response: Response,
    token: str = Query(..., min_length=8),
    x_forwarded_for: str | None = Header(default=None),
) -> dict[str, bool]:
    client_ip = _client_ip(x_forwarded_for)
    _enforce_rate_limit(ip=client_ip, token=token)
    return _bootstrap_session(token, response)


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    clear_session_cookie(response)
    return {"ok": True}
