#!/usr/bin/env python3
"""Seed CTFd with TeamAlpha/TeamBeta and a team_token challenge for integration tests."""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

import requests

CTFD_URL = os.environ.get("CTFD_URL", "http://localhost:8001").rstrip("/")
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "Password123!")
CHALLENGE_URL = os.environ.get("CHALLENGE_URL", "http://localhost:8002")
PLUGIN_SECRET = os.environ.get("TEAM_TOKEN_PLUGIN_SECRET", "dev-plugin-secret-for-testing")
CHALLENGE_NAME = os.environ.get("CHALLENGE_NAME", "Go Going Goen")
CHALLENGE_FLAG = os.environ.get("CHALLENGE_FLAG", "grey{integration_test_flag}")
ENV_OUTPUT = Path(os.environ.get("ENV_OUTPUT", "dev/integration/.env.integration"))


def wait_for_ctfd(timeout: float = 180) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            response = requests.get(f"{CTFD_URL}/setup", timeout=5)
            if response.status_code in (200, 302, 404):
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    raise RuntimeError("CTFd did not become ready in time")


def login(session: requests.Session) -> None:
    response = session.get(f"{CTFD_URL}/login")
    response.raise_for_status()
    match = re.search(r'name="nonce" type="hidden" value="([^"]+)"', response.text)
    if not match:
        raise RuntimeError("Could not find login nonce")
    session.post(
        f"{CTFD_URL}/login",
        data={"name": ADMIN_USER, "password": ADMIN_PASS, "nonce": match.group(1)},
        allow_redirects=True,
    )
    payload = session.get(f"{CTFD_URL}/api/v1/users/me").json()
    if not payload.get("success"):
        raise RuntimeError(f"Admin login failed: {payload}")


def csrf_headers(session: requests.Session) -> dict[str, str]:
    response = session.get(f"{CTFD_URL}/admin/challenges")
    response.raise_for_status()
    match = re.search(r"'csrfNonce': \"([^\"]+)\"", response.text)
    if not match:
        raise RuntimeError("Could not find CSRF nonce")
    return {"CSRF-Token": match.group(1), "Content-Type": "application/json"}


def api_json(session: requests.Session, method: str, path: str, **kwargs):
    headers = kwargs.pop("headers", {})
    merged = csrf_headers(session)
    merged.update(headers)
    response = session.request(method, f"{CTFD_URL}{path}", timeout=20, headers=merged, **kwargs)
    response.raise_for_status()
    return response.json()


def find_challenge(session: requests.Session, name: str):
    data = api_json(session, "GET", "/api/v1/challenges")
    for challenge in data.get("data", []):
        if challenge.get("name") == name:
            return challenge
    return None


def create_or_update_challenge(session: requests.Session) -> int:
    description = f"""## Go Going Goen

Your team token for this challenge is:

```
{{TEAM_TOKEN}}
```

Open the challenge app with your token:

[{CHALLENGE_URL}?token={{TEAM_TOKEN}}]({CHALLENGE_URL}?token={{TEAM_TOKEN}})
"""

    existing = find_challenge(session, CHALLENGE_NAME)
    payload = {
        "name": CHALLENGE_NAME,
        "category": "Team Token",
        "description": description,
        "value": 100,
        "state": "visible",
        "type": "team_token",
        "logic": "any",
        "function": "static",
    }

    if existing:
        challenge_id = existing["id"]
        api_json(session, "PATCH", f"/api/v1/challenges/{challenge_id}", json=payload)
        print(f"Updated challenge {CHALLENGE_NAME} (id={challenge_id})")
    else:
        data = api_json(session, "POST", "/api/v1/challenges", json=payload)
        challenge_id = data["data"]["id"]
        print(f"Created challenge {CHALLENGE_NAME} (id={challenge_id})")

    flags = api_json(session, "GET", f"/api/v1/challenges/{challenge_id}/flags").get("data", [])
    if not any(flag.get("content") == CHALLENGE_FLAG for flag in flags):
        api_json(
            session,
            "POST",
            "/api/v1/flags",
            json={
                "challenge_id": challenge_id,
                "content": CHALLENGE_FLAG,
                "type": "static",
                "data": "case_sensitive",
            },
        )
        print(f"Added flag to challenge {challenge_id}")

    return challenge_id


def ensure_test_accounts(session: requests.Session) -> None:
    accounts = [
        ("alpha", "alpha@example.com", "TeamAlpha", "Password123!"),
        ("beta", "beta@example.com", "TeamBeta", "Password123!"),
    ]

    users = {user["name"]: user for user in api_json(session, "GET", "/api/v1/users").get("data", [])}
    teams = {team["name"]: team for team in api_json(session, "GET", "/api/v1/teams").get("data", [])}

    for username, email, team_name, password in accounts:
        if team_name not in teams:
            team = api_json(
                session,
                "POST",
                "/api/v1/teams",
                json={"name": team_name, "password": "", "captain_id": None},
            )["data"]
            teams[team_name] = team
            print(f"Created team {team_name}")

        team_id = teams[team_name]["id"]
        if username not in users:
            user = api_json(
                session,
                "POST",
                "/api/v1/users",
                json={
                    "name": username,
                    "email": email,
                    "password": password,
                    "verified": True,
                },
            )["data"]
            users[username] = user
            print(f"Created user {username}")
            api_json(session, "PATCH", f"/api/v1/users/{user['id']}", json={"team_id": team_id})
            api_json(
                session,
                "POST",
                f"/api/v1/teams/{team_id}/members",
                json={"user_id": user["id"]},
            )
            print(f"Assigned {username} to {team_name}")
        elif users[username].get("team_id") != team_id:
            user_id = users[username]["id"]
            api_json(session, "PATCH", f"/api/v1/users/{user_id}", json={"team_id": team_id})
            api_json(
                session,
                "POST",
                f"/api/v1/teams/{team_id}/members",
                json={"user_id": user_id},
            )
            print(f"Updated user {username} team assignment")


def write_env_file(challenge_id: int) -> None:
    ENV_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"CTFD_CHALLENGE_ID={challenge_id}",
        f"TEAM_TOKEN_PLUGIN_SECRET={PLUGIN_SECRET}",
        f"CTFD_URL={CTFD_URL}",
        f"BACKEND_URL={CHALLENGE_URL}",
        "",
    ]
    ENV_OUTPUT.write_text("\n".join(lines))
    print(f"Wrote {ENV_OUTPUT}")


def main() -> None:
    print(f"Waiting for CTFd at {CTFD_URL} ...")
    wait_for_ctfd()

    session = requests.Session()
    print("Logging in as admin ...")
    login(session)

    print("Ensuring test teams and users ...")
    ensure_test_accounts(session)

    print("Creating Team Token challenge ...")
    challenge_id = create_or_update_challenge(session)
    write_env_file(challenge_id)

    print("")
    print("Seed complete.")
    print(f"  CTFd:         {CTFD_URL}")
    print(f"  Challenge:    {CHALLENGE_URL}")
    print(f"  Challenge id: {challenge_id}")
    print(f"  Test users:   alpha / Password123! (TeamAlpha)")
    print(f"                beta / Password123! (TeamBeta)")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Seed failed: {exc}", file=sys.stderr)
        sys.exit(1)
