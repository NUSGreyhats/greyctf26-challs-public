from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Mapping, Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_RESOLVE_PATH = "/plugins/team-token/api/v1/resolve"
SECRET_ENV_NAMES = ("CTFD_TEAM_TOKEN_PLUGIN_SECRET", "TEAM_TOKEN_PLUGIN_SECRET")


class TeamTokenError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TeamTokenResult:
    team_id: str
    challenge_id: str
    team_name: str | None = None


def normalize_token_line(line: str) -> str:
    text = line.strip()
    if text.lower().startswith("token "):
        text = text.split(None, 1)[1].strip()
    if not text:
        raise TeamTokenError("missing token")
    return text


def resolver_url_from_env(environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    override = env.get("CTFD_RESOLVE_URL")
    if override:
        return override
    base_url = env.get("CTFD_URL")
    if not base_url:
        raise TeamTokenError("missing CTFD_URL or CTFD_RESOLVE_URL")
    base_url = base_url.rstrip("/")
    if DEFAULT_RESOLVE_PATH in base_url:
        return base_url
    return base_url + DEFAULT_RESOLVE_PATH


def secret_from_env(environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    for name in SECRET_ENV_NAMES:
        secret = env.get(name)
        if secret:
            return secret
    raise TeamTokenError("missing CTFd team-token plugin secret")


def expected_challenge_id_from_env(environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    challenge_id = env.get("CTFD_TEAM_TOKEN_CHALLENGE_ID")
    if not challenge_id:
        raise TeamTokenError("missing CTFD_TEAM_TOKEN_CHALLENGE_ID")
    return str(challenge_id)


def validate_team_token(
    token: str,
    *,
    environ: Mapping[str, str] | None = None,
    timeout: float = 5.0,
) -> TeamTokenResult:
    env = os.environ if environ is None else environ
    expected_challenge_id = expected_challenge_id_from_env(env)
    payload = resolve_team_token(token, environ=env, timeout=timeout)

    if not payload.get("valid"):
        raise TeamTokenError("invalid token")
    if payload.get("solved"):
        raise TeamTokenError("challenge already solved for this team")

    challenge_id = _required_string(payload, "challenge_id")
    if challenge_id != expected_challenge_id:
        raise TeamTokenError("token is for a different challenge")

    return TeamTokenResult(
        team_id=_required_string(payload, "team_id"),
        challenge_id=challenge_id,
        team_name=_optional_string(payload, "team_name"),
    )


def resolve_team_token(
    token: str,
    *,
    environ: Mapping[str, str] | None = None,
    timeout: float = 5.0,
) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    url = resolver_url_from_env(env)
    secret = secret_from_env(env)
    query_separator = "&" if "?" in url else "?"
    request = Request(
        url + query_separator + urlencode({"token": token}),
        headers={"Authorization": f"Bearer {secret}", "Accept": "application/json"},
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
    except HTTPError as exc:
        raise TeamTokenError(f"resolver rejected token: http {exc.code}") from exc
    except URLError as exc:
        raise TeamTokenError(f"resolver unavailable: {exc.reason}") from exc
    except OSError as exc:
        raise TeamTokenError(f"resolver unavailable: {exc}") from exc

    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TeamTokenError("resolver returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise TeamTokenError("resolver returned invalid payload")
    return decoded


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None:
        raise TeamTokenError(f"resolver response missing {key}")
    return str(value)


def _optional_string(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return None if value is None else str(value)
