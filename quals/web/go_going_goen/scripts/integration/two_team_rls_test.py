#!/usr/bin/env python3
"""Two-team RLS integration test (AC-1 / PRD test T1)."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

from ctfd_helpers import (
    IntegrationError,
    bootstrap_session,
    fetch_team_tokens,
    resolve_token,
)

CTFD_URL = os.environ.get("CTFD_URL", "http://localhost:8001").rstrip("/")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8002").rstrip("/")
PLUGIN_SECRET = os.environ.get("TEAM_TOKEN_PLUGIN_SECRET", "dev-plugin-secret-for-testing")


class TestFailure(Exception):
    pass


def submit_wordlist_guess(session: requests.Session, backend_url: str) -> requests.Response:
    root = Path(__file__).resolve().parents[2]
    wordlist = root / "src/backend/app/stages/stage1/wordlist.txt"
    candidates = [
        line.strip().lower()
        for line in wordlist.read_text().splitlines()
        if len(line.strip()) == 5
    ]
    for word in candidates:
        response = session.post(
            f"{backend_url}/api/v1/pinpoint/guess",
            json={"guess": word},
            timeout=15,
        )
        if response.status_code == 200:
            return response
        if response.status_code == 400:
            body = response.json()
            if body.get("error") == "invalid_guess":
                continue
        raise IntegrationError(
            f"Unexpected guess response ({response.status_code}): {response.text}"
        )
    raise IntegrationError("Could not find a wordlist guess accepted by the backend")


def wait_for_backend(timeout: float = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            response = requests.get(f"{BACKEND_URL}/healthz", timeout=5)
            if response.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    raise TestFailure("Backend did not become ready in time")


def check(name: str, condition: bool, detail: str = "", failures: list[str] | None = None) -> None:
    if condition:
        print(f"PASS  {name}")
    else:
        msg = f"FAIL  {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)
        if failures is not None:
            failures.append(name)


def main() -> int:
    failures: list[str] = []
    print(f"Waiting for backend at {BACKEND_URL} ...")
    wait_for_backend()

    print("Fetching team tokens from CTFd ...")
    token_a, token_b = fetch_team_tokens(CTFD_URL)
    check("Tokens distinct", token_a != token_b, failures=failures)

    resolved_a = resolve_token(CTFD_URL, PLUGIN_SECRET, token_a)
    check(
        "Resolve token A",
        resolved_a.get("valid") is True and resolved_a.get("team_id"),
        json.dumps(resolved_a),
        failures,
    )

    print("Bootstrapping backend sessions ...")
    session_a = bootstrap_session(BACKEND_URL, token_a)
    session_b = bootstrap_session(BACKEND_URL, token_b)

    me_a = session_a.get(f"{BACKEND_URL}/api/me").json()
    me_b = session_b.get(f"{BACKEND_URL}/api/me").json()
    check("Team A has session user", me_a.get("user_id") is not None, str(me_a), failures)
    check("Team B has session user", me_b.get("user_id") is not None, str(me_b), failures)
    check(
        "Per-team user ids (RLS scoped)",
        me_a.get("user_id") is not None and me_b.get("user_id") is not None,
        f"A={me_a.get('user_id')} B={me_b.get('user_id')}",
        failures,
    )
    check(
        "No team metadata in /api/me",
        "team_id" not in me_a and "team_name" not in me_a,
        str(me_a),
        failures,
    )

    # Team A makes progress in Stage 1.
    guess_resp = submit_wordlist_guess(session_a, BACKEND_URL)
    check("Team A guess accepted", guess_resp.status_code == 200, guess_resp.text, failures)

    status_a = session_a.get(f"{BACKEND_URL}/api/v1/pinpoint/status").json()
    status_b = session_b.get(f"{BACKEND_URL}/api/v1/pinpoint/status").json()
    guesses_a = status_a.get("guesses_used", 0)
    guesses_b = status_b.get("guesses_used", 0)
    check(
        "Team A has guesses recorded",
        guesses_a >= 1,
        f"guesses_used={guesses_a}",
        failures,
    )
    check(
        "Team B isolated (no guesses from A)",
        guesses_b == 0,
        f"guesses_used={guesses_b} (expected 0)",
        failures,
    )

    check(
        "Pinpoint status differs between teams",
        status_a != status_b,
        f"A={status_a} B={status_b}",
        failures,
    )

    # Team B cannot call admin reset without admin token.
    reset_b = session_b.post(
        f"{BACKEND_URL}/api/admin/reset-all",
        headers={"Authorization": "Bearer not-the-admin-token"},
        timeout=15,
    )
    check(
        "Team B cannot admin reset",
        reset_b.status_code == 401,
        f"status={reset_b.status_code} body={reset_b.text}",
        failures,
    )

    status_a_after = session_a.get(f"{BACKEND_URL}/api/v1/pinpoint/status").json()
    check(
        "Team A state survives Team B activity",
        status_a_after.get("guesses_used", 0) >= guesses_a,
        json.dumps(status_a_after),
        failures,
    )

    print("")
    if failures:
        print(f"FAILED ({len(failures)}): {', '.join(failures)}")
        return 1
    print("All integration checks passed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (TestFailure, IntegrationError, requests.RequestException) as exc:
        print(f"Integration test error: {exc}", file=sys.stderr)
        sys.exit(1)
