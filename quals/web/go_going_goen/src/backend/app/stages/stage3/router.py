from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .models import TangoCell
from .service import (
    InvalidGridError,
    NotEnoughCreditsError,
    SubmissionGate,
    TangoService,
    TangoValidationError,
    TooManySubmissionsError,
)

class TangoSubmitRequest(BaseModel):
    grid: list[list[TangoCell]] = Field(min_length=6, max_length=6)

class TangoSubmitResponse(BaseModel):
    result: Literal["accepted"]
    dollars_awarded: int
    attempt_id: str

class BuyFlagResponse(BaseModel):
    result: Literal["win"]
    flag: str

ServiceDependency = Callable[[], TangoService]
UserDependency = Callable[..., int]
GateDependency = Callable[[], SubmissionGate]

def create_tango_router(
    *,
    get_service: ServiceDependency,
    get_current_user_id: UserDependency,
    get_submission_gate: GateDependency,
) -> APIRouter:
    router = APIRouter(prefix="/api/v3/tango", tags=["tango"])

    @router.get("/status")
    def status_endpoint(
        user_id: int = Depends(get_current_user_id),
        service: TangoService = Depends(get_service),
    ) -> dict[str, object]:
        return asdict(service.get_status(user_id))

    @router.post("/submit", response_model=TangoSubmitResponse)
    async def submit_endpoint(
        payload: TangoSubmitRequest,
        user_id: int = Depends(get_current_user_id),
        service: TangoService = Depends(get_service),
        gate: SubmissionGate = Depends(get_submission_gate),
    ) -> TangoSubmitResponse | JSONResponse:
        try:
            async with gate.acquire(user_id, timeout=0.25):
                result = await run_in_threadpool(service.submit_grid, user_id, payload.grid)
        except TooManySubmissionsError:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"error": "too_many_submissions", "message": "Too many submissions."},
            )
        except InvalidGridError as exc:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "invalid_grid", "message": str(exc), "attempt_id": str(exc.attempt_id)},
            )
        except TangoValidationError as exc:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": "validation_error", "message": str(exc), "attempt_id": str(exc.attempt_id)},
            )
        return TangoSubmitResponse(
            result=result.result,
            dollars_awarded=result.dollars_awarded,
            attempt_id=str(result.attempt_id),
        )

    @router.get("/ledger")
    def ledger_endpoint(
        user_id: int = Depends(get_current_user_id),
        service: TangoService = Depends(get_service),
    ) -> dict[str, object]:
        return asdict(service.get_ledger(user_id))

    @router.post("/ledger/refresh")
    def refresh_ledger_endpoint(
        user_id: int = Depends(get_current_user_id),
        service: TangoService = Depends(get_service),
    ) -> dict[str, object]:
        return asdict(service.refresh_ledger(user_id))

    @router.post("/buy-flag", response_model=BuyFlagResponse)
    def buy_flag_endpoint(
        user_id: int = Depends(get_current_user_id),
        service: TangoService = Depends(get_service),
    ) -> BuyFlagResponse | JSONResponse:
        try:
            result = service.buy_flag(user_id)
        except NotEnoughCreditsError as exc:
            return JSONResponse(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                content={"error": "not_enough_credits", "message": str(exc)},
            )
        return BuyFlagResponse(result=result.result, flag=result.flag)

    @router.get("/attempt/{attempt_id}", response_model=None)
    def attempt_endpoint(
        attempt_id: UUID,
        user_id: int = Depends(get_current_user_id),
        service: TangoService = Depends(get_service),
    ) -> dict[str, object] | JSONResponse:
        attempt = service.get_attempt(user_id, attempt_id)
        if attempt is None:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": "attempt_not_found", "message": "Attempt not found."},
            )
        return asdict(attempt)

    @router.post("/reset")
    def reset_endpoint(
        user_id: int = Depends(get_current_user_id),
        service: TangoService = Depends(get_service),
    ) -> dict[str, object]:
        return asdict(service.reset(user_id))

    return router
