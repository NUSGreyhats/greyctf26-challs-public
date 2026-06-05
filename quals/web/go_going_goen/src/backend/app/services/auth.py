from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, Response

from app.core.config import settings
from app.core.exceptions import AppError
from app.core import team_context
from app.db.session import Database
from app.models.auth import SessionUser
from app.services.ctfd_token import resolve_team_token, token_fingerprint
from app.services.instance import InstanceService

COOKIE_NAME = "ggg_session"
SINGLETON_PASSWORD_HASH = "singleton-auth-disabled"


def _b64url_encode(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _b64url_decode(value: str) -> str:
    return base64.urlsafe_b64decode(f"{value}{'=' * (-len(value) % 4)}").decode()


def _sign(payload: str) -> str:
    return hmac.new(
        settings.session_secret.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()


class AuthService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def ensure_team_user(self, internal_team_id: str) -> SessionUser:
        row = self._db.fetch_one(
            "SELECT id, username FROM users WHERE username = %s",
            [settings.singleton_username],
        )
        if row is None:
            self._db.execute(
                """
                INSERT INTO users (team_id, username, password_hash)
                VALUES (current_setting('app.team_id'), %s, %s)
                ON CONFLICT (team_id, username) DO NOTHING
                """,
                [settings.singleton_username, SINGLETON_PASSWORD_HASH],
            )
            row = self._db.fetch_one(
                "SELECT id, username FROM users WHERE username = %s",
                [settings.singleton_username],
            )
        if row is None:
            raise AppError(
                status_code=500,
                error="auth_bootstrap_failed",
                message="Could not bootstrap the team user.",
            )

        user_id = int(row["id"])
        self._db.execute(
            """
            INSERT INTO user_progress (team_id, user_id)
            VALUES (current_setting('app.team_id'), %s)
            ON CONFLICT (user_id) DO NOTHING
            """,
            [user_id],
        )
        return SessionUser(
            user_id=user_id,
            username=str(row["username"]),
            team_id=internal_team_id,
        )


def create_session_from_token(token: str) -> tuple[SessionUser, str]:
    resolved = resolve_team_token(token)
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.session_ttl_days)

    with Database(team_id=resolved.internal_team_id) as db:
        auth = AuthService(db)
        user = auth.ensure_team_user(resolved.internal_team_id)
        InstanceService(db).ensure_seed()
        db.execute(
            """
            INSERT INTO auth_sessions (id, team_id, token_fingerprint, expires_at)
            VALUES (%s, %s, %s, %s)
            """,
            [
                session_id,
                resolved.internal_team_id,
                token_fingerprint(token),
                expires_at,
            ],
        )

    return user, session_id


def read_session_id(raw_cookie: str | None) -> str | None:
    if not raw_cookie or "." not in raw_cookie:
        return None

    payload, signature = raw_cookie.split(".", 1)
    if not hmac.compare_digest(_sign(payload), signature):
        return None

    try:
        data = json.loads(_b64url_decode(payload))
    except (ValueError, json.JSONDecodeError):
        return None

    session_id = data.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    return session_id


def load_session_user(session_id: str) -> SessionUser | None:
    with Database.bootstrap() as db:
        row = db.fetch_one(
            """
            SELECT team_id, expires_at
            FROM auth_sessions
            WHERE id = %s
            """,
            [session_id],
        )
        if row is None:
            return None

        expires_at = row["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            db.execute("DELETE FROM auth_sessions WHERE id = %s", [session_id])
            return None

        internal_team_id = str(row["team_id"])

    with Database(team_id=internal_team_id) as db:
        return AuthService(db).ensure_team_user(internal_team_id)


def set_session_cookie(response: Response, session_id: str) -> None:
    payload = _b64url_encode(json.dumps({"session_id": session_id}))
    response.set_cookie(
        key=COOKIE_NAME,
        value=f"{payload}.{_sign(payload)}",
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax")


def get_optional_session_user(
    session_cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> SessionUser | None:
    session_id = read_session_id(session_cookie)
    if session_id is None:
        return None
    user = load_session_user(session_id)
    if user is not None:
        team_context.set_team_id(user.team_id)
    return user


def require_session_user(
    user: SessionUser | None = Depends(get_optional_session_user),
) -> SessionUser:
    if user is None:
        raise AppError(
            status_code=401,
            error="unauthorized",
            message="Authentication required.",
        )
    team_context.set_team_id(user.team_id)
    return user
