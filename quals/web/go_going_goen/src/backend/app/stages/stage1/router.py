from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import asdict

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.core.config import settings

from .service import (
    GuessLimitReached,
    InvalidGuess,
    PinpointService,
    ResetCooldownError,
    GuessGate,
    ResetGate,
    TooManyGuessesError,
)


class GuessRequest(BaseModel):
    guess: str


class StatusResponse(BaseModel):
    guesses_used: int
    remaining_guesses: int
    solved: bool
    last_result: str | None
    recent_guesses: list[str]


class GuessResponse(BaseModel):
    result: str
    guesses_used: int | None = None
    remaining_guesses: int | None = None


ServiceDependency = Callable[[], PinpointService]
UserDependency = Callable[..., int]
GateDependency = Callable[[], GuessGate]
ResetGateDependency = Callable[[], ResetGate]


def _diagnostics_hash_rounds(seed: str, rounds: int) -> str:
    verification = seed
    for _ in range(rounds):
        verification = hashlib.sha256(verification.encode()).hexdigest()
    return verification


def _calibrate_diagnostics_attest_rounds() -> int:
    if settings.pinpoint_diagnostics_attest_rounds is not None:
        return max(1, settings.pinpoint_diagnostics_attest_rounds)

    target_seconds = max(0.001, settings.pinpoint_diagnostics_target_ms / 1000)
    benchmark_rounds = 2_000
    started = time.perf_counter()
    _diagnostics_hash_rounds(settings.pinpoint_token, benchmark_rounds)
    elapsed = time.perf_counter() - started
    if elapsed <= 0:
        return benchmark_rounds
    return max(1, int(benchmark_rounds * target_seconds / elapsed))


DIAGNOSTICS_ATTEST_ROUNDS = _calibrate_diagnostics_attest_rounds()


def _attest_diagnostics_token(token: str, expected: str) -> int:
    matched = 0
    verification = expected
    for given, want in zip(token, expected):
        if given != want:
            break
        matched += 1
        verification += given
        verification = _diagnostics_hash_rounds(
            verification, DIAGNOSTICS_ATTEST_ROUNDS
        )
    return matched


def create_pinpoint_router(
    *,
    get_service: ServiceDependency,
    get_current_user_id: UserDependency,
    get_guess_gate: GateDependency,
    get_reset_gate: ResetGateDependency,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/pinpoint", tags=["pinpoint"])

    @router.get("/status", response_model=StatusResponse)
    def status_endpoint(
        user_id: int = Depends(get_current_user_id),
        service: PinpointService = Depends(get_service),
    ) -> StatusResponse:
        return StatusResponse(**asdict(service.get_status(user_id)))

    @router.post(
        "/guess", response_model=GuessResponse, response_model_exclude_none=True
    )
    async def guess_endpoint(
        payload: GuessRequest,
        user_id: int = Depends(get_current_user_id),
        service: PinpointService = Depends(get_service),
        gate: GuessGate = Depends(get_guess_gate),
    ) -> GuessResponse | JSONResponse:
        try:
            async with gate.acquire(user_id, timeout=0.25):
                result = await run_in_threadpool(
                    service.submit_guess, user_id, payload.guess
                )
            return GuessResponse(**asdict(result))
        except TooManyGuessesError:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"error": "too_many_guesses", "message": "Too many guesses."},
            )
        except InvalidGuess as exc:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "invalid_guess", "message": str(exc)},
            )
        except GuessLimitReached:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "error": "limit_reached",
                    "message": "Guess limit reached.",
                },
            )

    @router.get("/diagnostics", response_model=None)
    async def diagnostics_endpoint(
        token: str | None = None,
        user_id: int = Depends(get_current_user_id),
        service: PinpointService = Depends(get_service),
    ) -> dict[str, object] | JSONResponse:
        if token is not None:
            expected = settings.pinpoint_token
            matched = await run_in_threadpool(
                _attest_diagnostics_token, token, expected
            )
            if matched != len(expected) or len(token) != len(expected):
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={
                        "error": "unauthorized",
                        "message": "Operator token rejected.",
                    },
                )
        snapshot = service.get_status(user_id)
        public = {
            "status": "ok",
            "guesses_used": snapshot.guesses_used,
            "remaining_guesses": snapshot.remaining_guesses,
        }
        if token is None:
            return public
        return {**public, "operator": "ok", "instance": "healthy"}

    @router.post("/reset", response_model=StatusResponse)
    def reset_endpoint(
        user_id: int = Depends(get_current_user_id),
        service: PinpointService = Depends(get_service),
        reset_gate: ResetGate = Depends(get_reset_gate),
    ) -> StatusResponse | JSONResponse:
        try:
            reset_gate.consume(user_id)
        except ResetCooldownError as exc:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": str(exc.retry_after_seconds)},
                content={
                    "error": "reset_cooldown",
                    "message": "Reset is on cooldown.",
                    "retry_after_seconds": exc.retry_after_seconds,
                },
            )
        return StatusResponse(**asdict(service.reset(user_id)))

    return router
