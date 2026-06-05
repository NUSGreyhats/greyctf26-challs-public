from __future__ import annotations

from dataclasses import replace
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.stages.stage1.models import PinpointUserState
from app.stages.stage1.router import create_pinpoint_router
from app.stages.stage1.service import (
    PinpointService,
    GuessGate,
    ResetGate,
    TooManyGuessesError,
)
from app.stages.stage1.wordbank import WordBank

from .test_pinpoint_service import InMemoryRepository, ProgressGatewayStub


def build_client() -> tuple[TestClient, InMemoryRepository, ProgressGatewayStub]:
    repository = InMemoryRepository()
    progress = ProgressGatewayStub()
    service = PinpointService(
        repository=repository,
        progress_gateway=progress,
        wordbank=WordBank(
            ["crane", "slate", "shard", "flint", "proud", "gleam"], secret="test-pinpoint-secret", minimum_size=1
        ),
        instance_seed="router-seed",
    )

    app = FastAPI()
    app.include_router(
        create_pinpoint_router(
            get_service=lambda: service,
            get_current_user_id=lambda: 41,
            get_guess_gate=lambda: GuessGate(capacity=8),
            get_reset_gate=lambda: ResetGate(cooldown_seconds=0),
        )
    )
    return TestClient(app), repository, progress


class BusyGuessGate:
    @asynccontextmanager
    async def acquire(self, _user_id: int, timeout: float = 0.25):
        raise TooManyGuessesError()
        yield


def test_status_endpoint_returns_stage_state() -> None:
    client, _, _ = build_client()

    response = client.get("/api/v1/pinpoint/status")

    assert response.status_code == 200
    assert response.json() == {
        "guesses_used": 0,
        "remaining_guesses": 5,
        "solved": False,
        "last_result": None,
        "recent_guesses": [],
    }


def test_diagnostics_without_token_returns_public_snapshot() -> None:
    client, _, _ = build_client()

    response = client.get("/api/v1/pinpoint/diagnostics")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "operator" not in body


def test_diagnostics_with_wrong_token_returns_401() -> None:
    client, _, _ = build_client()

    response = client.get(
        "/api/v1/pinpoint/diagnostics", params={"token": "not-the-secret"}
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": "unauthorized",
        "message": "Operator token rejected.",
    }


def test_diagnostics_with_correct_token_returns_operator_payload() -> None:
    from app.core.config import settings as live_settings

    expected_token = live_settings.pinpoint_token
    assert len(expected_token) == 8

    client, _, _ = build_client()

    response = client.get(
        "/api/v1/pinpoint/diagnostics", params={"token": expected_token}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["operator"] == "ok"
    assert body["instance"] == "healthy"


def test_pinpoint_token_is_normalized_to_8_hex_chars() -> None:
    from app.core.config import Settings

    short = Settings(pinpoint_secret="x").pinpoint_token
    long = Settings(pinpoint_secret="x" * 1000).pinpoint_token
    assert len(short) == len(long) == 8
    assert all(ch in "0123456789abcdef" for ch in short)
    assert short != long


def test_diagnostics_response_time_scales_with_matched_prefix() -> None:
    import time
    from app.core.config import settings as live_settings

    expected = live_settings.pinpoint_token
    client, _, _ = build_client()

    samples_per_prefix: dict[int, list[float]] = {0: [], 2: [], 4: [], 8: []}
    for prefix_len in samples_per_prefix:
        for _ in range(5):
            token = expected[:prefix_len] + "z" * (8 - prefix_len)
            t0 = time.perf_counter()
            client.get("/api/v1/pinpoint/diagnostics", params={"token": token})
            samples_per_prefix[prefix_len].append(time.perf_counter() - t0)

    median = lambda xs: sorted(xs)[len(xs) // 2]
    t0 = median(samples_per_prefix[0])
    t2 = median(samples_per_prefix[2])
    t4 = median(samples_per_prefix[4])
    t8 = median(samples_per_prefix[8])
    assert t8 - t0 > 0.006, (samples_per_prefix, t0, t8)
    assert t4 > t2 > t0, (t0, t2, t4, t8)


def test_guess_endpoint_returns_limit_error_shape() -> None:
    client, repository, _ = build_client()
    repository.create_user_state(
        replace(
            repository.rows.get(41) or service_state(41, "crane"),
            guesses_used=5,
        )
    )

    response = client.post("/api/v1/pinpoint/guess", json={"guess": "crane"})

    assert response.status_code == 409
    assert response.json() == {
        "error": "limit_reached",
        "message": "Guess limit reached.",
    }


def test_guess_endpoint_returns_correct_result_on_solve() -> None:
    client, repository, _ = build_client()
    repository.create_user_state(service_state(41, "crane"))

    response = client.post("/api/v1/pinpoint/guess", json={"guess": "crane"})

    assert response.status_code == 200
    assert response.json() == {
        "result": "correct",
    }


def test_guess_endpoint_returns_invalid_guess_shape() -> None:
    client, _, _ = build_client()

    response = client.post("/api/v1/pinpoint/guess", json={"guess": "12"})

    assert response.status_code == 400
    assert response.json() == {
        "error": "invalid_guess",
        "message": "Guesses must be exactly 5 letters",
    }


def test_guess_endpoint_returns_too_many_guesses_shape() -> None:
    repository = InMemoryRepository()
    progress = ProgressGatewayStub()
    service = PinpointService(
        repository=repository,
        progress_gateway=progress,
        wordbank=WordBank(
            ["crane", "slate", "shard", "flint", "proud", "gleam"], secret="test-pinpoint-secret", minimum_size=1
        ),
        instance_seed="router-seed",
    )

    app = FastAPI()
    app.include_router(
        create_pinpoint_router(
            get_service=lambda: service,
            get_current_user_id=lambda: 41,
            get_guess_gate=lambda: BusyGuessGate(),
            get_reset_gate=lambda: ResetGate(cooldown_seconds=0),
        )
    )
    client = TestClient(app)

    response = client.post("/api/v1/pinpoint/guess", json={"guess": "crane"})

    assert response.status_code == 429
    assert response.json() == {
        "error": "too_many_guesses",
        "message": "Too many guesses.",
    }


def test_guess_endpoint_rejects_words_outside_wordbank() -> None:
    client, repository, _ = build_client()
    repository.create_user_state(service_state(41, "crane"))

    response = client.post("/api/v1/pinpoint/guess", json={"guess": "zzzzz"})

    assert response.status_code == 400
    assert response.json() == {
        "error": "invalid_guess",
        "message": "Guesses must be in the wordlist",
    }
    assert repository.rows[41].guesses_used == 0


def test_reset_endpoint_rotates_answer_and_clears_mutable_fields() -> None:
    client, repository, _ = build_client()
    repository.create_user_state(
        replace(
            service_state(41, "crane"),
            guesses_used=3,
            solved=True,
            last_result="correct",
        )
    )

    response = client.post("/api/v1/pinpoint/reset")

    assert response.status_code == 200
    assert response.json() == {
        "guesses_used": 0,
        "remaining_guesses": 5,
        "solved": False,
        "last_result": None,
        "recent_guesses": [],
    }
    assert repository.rows[41].puzzle_answer != "crane"


def test_reset_endpoint_enforces_cooldown() -> None:
    repository = InMemoryRepository()
    progress = ProgressGatewayStub()
    service = PinpointService(
        repository=repository,
        progress_gateway=progress,
        wordbank=WordBank(
            ["crane", "slate", "shard", "flint", "proud", "gleam"], secret="test-pinpoint-secret", minimum_size=1
        ),
        instance_seed="router-seed",
    )
    repository.create_user_state(service_state(41, "crane"))

    reset_gate = ResetGate(cooldown_seconds=60)
    app = FastAPI()
    app.include_router(
        create_pinpoint_router(
            get_service=lambda: service,
            get_current_user_id=lambda: 41,
            get_guess_gate=lambda: GuessGate(capacity=8),
            get_reset_gate=lambda: reset_gate,
        )
    )
    client = TestClient(app)

    first = client.post("/api/v1/pinpoint/reset")
    assert first.status_code == 200

    second = client.post("/api/v1/pinpoint/reset")
    assert second.status_code == 429
    body = second.json()
    assert body["error"] == "reset_cooldown"
    assert 0 < body["retry_after_seconds"] <= 60


def service_state(user_id: int, answer: str) -> PinpointUserState:
    return PinpointUserState(
        user_id=user_id,
        guesses_used=0,
        solved=False,
        puzzle_answer=answer,
        last_result=None,
    )
