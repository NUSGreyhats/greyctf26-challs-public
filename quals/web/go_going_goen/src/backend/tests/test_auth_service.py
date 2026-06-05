from __future__ import annotations

import json
from unittest.mock import patch

from fastapi import Response

from app.core.config import settings
from app.core.exceptions import AppError
from app.services.auth import read_session_id, set_session_cookie
from app.services.ctfd_token import clear_resolve_cache_for_testing, resolve_team_token


def test_read_session_id_round_trip() -> None:
    response = Response()
    set_session_cookie(response, "session-abc")
    cookie = response.headers["set-cookie"].split("=", 1)[1].split(";", 1)[0]

    assert read_session_id(cookie) == "session-abc"


def test_read_session_id_rejects_tampered_cookie() -> None:
    response = Response()
    set_session_cookie(response, "valid-session-id")
    cookie = response.headers["set-cookie"].split("=", 1)[1].split(";", 1)[0]
    payload, _signature = cookie.rsplit(".", 1)
    tampered = f"{payload}.{'0' * 64}"

    assert read_session_id(tampered) is None


def test_resolve_team_token_calls_ctfd(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ctfd_resolve_url", "https://ctfd.example/resolve")
    monkeypatch.setattr(settings, "ctfd_team_token_plugin_secret", "secret")
    monkeypatch.setattr(settings, "ctfd_challenge_id", 7)
    clear_resolve_cache_for_testing()

    payload = json.dumps(
        {"valid": True, "team_id": 42, "team_name": "TeamAlpha", "challenge_id": 7}
    ).encode()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return payload

    with patch("urllib.request.urlopen", return_value=FakeResponse()):
        resolved = resolve_team_token("tt_valid_token_abc")

    assert resolved.ctfd_team_id == 42
    assert resolved.ctfd_challenge_id == 7
    assert resolved.internal_team_id == settings.derive_team_id(42, 7)


def test_resolve_rejects_wrong_challenge_id(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ctfd_resolve_url", "https://ctfd.example/resolve")
    monkeypatch.setattr(settings, "ctfd_team_token_plugin_secret", "secret")
    monkeypatch.setattr(settings, "ctfd_challenge_id", 9)
    clear_resolve_cache_for_testing()

    payload = json.dumps(
        {"valid": True, "team_id": 42, "team_name": "TeamAlpha", "challenge_id": 7}
    ).encode()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return payload

    with patch("urllib.request.urlopen", return_value=FakeResponse()):
        try:
            resolve_team_token("tt_wrong_challenge")
            assert False, "expected AppError"
        except AppError as exc:
            assert exc.status_code == 401
            assert exc.error == "invalid_token"


def test_resolve_rejects_invalid_ctfd_response(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ctfd_resolve_url", "https://ctfd.example/resolve")
    monkeypatch.setattr(settings, "ctfd_team_token_plugin_secret", "secret")
    monkeypatch.setattr(settings, "ctfd_challenge_id", 7)
    clear_resolve_cache_for_testing()

    payload = json.dumps({"valid": False}).encode()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return payload

    with patch("urllib.request.urlopen", return_value=FakeResponse()):
        try:
            resolve_team_token("tt_invalid_token")
            assert False, "expected AppError"
        except AppError as exc:
            assert exc.status_code == 401
            assert exc.error == "invalid_token"
