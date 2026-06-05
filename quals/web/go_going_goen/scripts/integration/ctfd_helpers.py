"""Shared helpers for integration tests against CTFd + challenge backend."""

from __future__ import annotations

import re

import requests

CHALLENGE_NAME = "Go Going Goen"


class IntegrationError(Exception):
    pass


def login(session: requests.Session, ctfd_url: str, username: str, password: str) -> None:
    response = session.get(f"{ctfd_url}/login")
    response.raise_for_status()
    match = re.search(r'name="nonce" type="hidden" value="([^"]+)"', response.text)
    if not match:
        raise IntegrationError("Could not find login nonce")
    session.post(
        f"{ctfd_url}/login",
        data={"name": username, "password": password, "nonce": match.group(1)},
        allow_redirects=True,
    )
    payload = session.get(f"{ctfd_url}/api/v1/users/me").json()
    if not payload.get("success"):
        raise IntegrationError(f"Login failed for {username}")


def get_challenge_id(session: requests.Session, ctfd_url: str) -> int:
    data = session.get(f"{ctfd_url}/api/v1/challenges").json()
    for challenge in data.get("data", []):
        if challenge.get("name") == CHALLENGE_NAME:
            return challenge["id"]
    raise IntegrationError(f"Challenge {CHALLENGE_NAME!r} not found")


def open_challenge(session: requests.Session, ctfd_url: str, challenge_id: int) -> dict:
    response = session.get(f"{ctfd_url}/api/v1/challenges/{challenge_id}")
    payload = response.json()
    if not payload.get("success"):
        raise IntegrationError(f"Could not open challenge {challenge_id}: {payload}")
    return payload["data"]


def extract_token(description: str) -> str:
    for line in description.splitlines():
        line = line.strip().strip("`")
        if line.startswith("tt_"):
            return line
    if "tt_" in description:
        start = description.index("tt_")
        return description[start : start + 46].split()[0]
    raise IntegrationError("Could not find tt_ token in description")


def fetch_team_tokens(ctfd_url: str) -> tuple[str, str]:
    session_a = requests.Session()
    session_b = requests.Session()
    login(session_a, ctfd_url, "alpha", "Password123!")
    login(session_b, ctfd_url, "beta", "Password123!")

    challenge_id = get_challenge_id(session_a, ctfd_url)
    token_a = extract_token(open_challenge(session_a, ctfd_url, challenge_id)["description"])
    token_b = extract_token(open_challenge(session_b, ctfd_url, challenge_id)["description"])
    if token_a == token_b:
        raise IntegrationError("Expected distinct tokens for TeamAlpha and TeamBeta")
    return token_a, token_b


def bootstrap_session(backend_url: str, token: str) -> requests.Session:
    session = requests.Session()
    response = session.post(
        f"{backend_url}/api/auth/session",
        json={"token": token},
        timeout=15,
    )
    if response.status_code != 200:
        raise IntegrationError(f"Session bootstrap failed ({response.status_code}): {response.text}")
    payload = response.json()
    if not payload.get("authenticated"):
        raise IntegrationError(f"Session not authenticated: {payload}")
    if payload.get("team_name") or payload.get("team_id"):
        raise IntegrationError(f"Backend leaked team metadata: {payload}")
    return session


def resolve_token(ctfd_url: str, plugin_secret: str, token: str) -> dict:
    response = requests.get(
        f"{ctfd_url}/plugins/team-token/api/v1/resolve",
        params={"token": token},
        headers={"Authorization": f"Bearer {plugin_secret}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()
