from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from app.core.config import settings
from app.core.exceptions import AppError

RESOLVE_CACHE_TTL_SECONDS = 600


@dataclass(frozen=True)
class ResolvedTeamToken:
    internal_team_id: str
    ctfd_team_id: int
    ctfd_challenge_id: int


@dataclass
class _CacheEntry:
    resolved: ResolvedTeamToken
    expires_at: float


_resolve_cache: dict[str, _CacheEntry] = {}


def token_fingerprint(token: str) -> str:
    import hashlib

    return hashlib.sha256(token.encode()).hexdigest()[:16]


def is_plausible_team_token(token: str) -> bool:
    return token.startswith("tt_") and len(token) >= 12


def resolve_team_token(token: str) -> ResolvedTeamToken:
    if not is_plausible_team_token(token):
        raise AppError(
            status_code=401,
            error="invalid_token",
            message="Authentication failed.",
        )

    cached = _resolve_cache.get(token)
    if cached is not None and cached.expires_at > time.time():
        return cached.resolved

    if not settings.ctfd_resolve_url or not settings.ctfd_team_token_plugin_secret:
        raise AppError(
            status_code=503,
            error="upstream_unavailable",
            message="Authentication service unavailable.",
        )
    if settings.ctfd_challenge_id is None:
        raise AppError(
            status_code=503,
            error="upstream_unavailable",
            message="Authentication service unavailable.",
        )

    query = urllib.parse.urlencode({"token": token})
    url = f"{settings.ctfd_resolve_url.rstrip('/')}?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {settings.ctfd_team_token_plugin_secret}",
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise AppError(
            status_code=503,
            error="upstream_unavailable",
            message="Authentication service unavailable.",
        ) from exc

    if not payload.get("valid"):
        raise AppError(
            status_code=401,
            error="invalid_token",
            message="Authentication failed.",
        )

    ctfd_team_id = int(payload["team_id"])
    ctfd_challenge_id = int(payload["challenge_id"])
    if ctfd_challenge_id != settings.ctfd_challenge_id:
        raise AppError(
            status_code=401,
            error="invalid_token",
            message="Authentication failed.",
        )

    resolved = ResolvedTeamToken(
        internal_team_id=settings.derive_team_id(ctfd_team_id, ctfd_challenge_id),
        ctfd_team_id=ctfd_team_id,
        ctfd_challenge_id=ctfd_challenge_id,
    )
    _resolve_cache[token] = _CacheEntry(
        resolved=resolved,
        expires_at=time.time() + RESOLVE_CACHE_TTL_SECONDS,
    )
    return resolved


def clear_resolve_cache_for_testing() -> None:
    _resolve_cache.clear()
