from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from starlette.concurrency import run_in_threadpool

from .constants import ADD_BATCH_MAX
from .models import BoardSnapshot, QueenPosition
from .service import (
    InvalidBoardError,
    OutOfBoundsError,
    QueensService,
    SubmissionGate,
    TooManySubmissionsError,
)

class QueenSpec(BaseModel):
    row: int
    col: int

class QueenMutationRequest(BaseModel):
    row: int
    col: int

class QueenAddRequest(BaseModel):
    row: int | None = None
    col: int | None = None
    queens: list[QueenSpec] | None = Field(default=None, max_length=ADD_BATCH_MAX)

    @model_validator(mode="after")
    def _exactly_one_shape(self) -> "QueenAddRequest":
        single = self.row is not None and self.col is not None
        batch = self.queens is not None
        if single == batch:
            raise ValueError(
                "Provide either {row, col} for a single queen or "
                "{queens: [...]} for a batch (not both, not neither)."
            )
        return self

class QueenPositionResponse(BaseModel):
    row: int
    col: int

class SubmissionResponse(BaseModel):
    status: str
    progress_pct: int
    last_result: str | None
    last_submitted_at: str | None = None

class BoardResponse(BaseModel):
    size: int
    queens: list[QueenPositionResponse]
    total_queens: int
    submission: SubmissionResponse

class MutationResponse(BaseModel):
    ok: bool
    total_queens: int

class SubmitResponse(BaseModel):
    result: str
    total_queens: int

ServiceDependency = Callable[[], QueensService]
UserDependency = Callable[..., int]
GateDependency = Callable[[], SubmissionGate]

def create_queens_router(
    *,
    get_service: ServiceDependency,
    get_current_user_id: UserDependency,
    get_submission_gate: GateDependency,
) -> APIRouter:
    router = APIRouter(prefix="/api/v2/queens", tags=["queens"])

    @router.get("/board", response_model=BoardResponse)
    def board_endpoint(
        user_id: int = Depends(get_current_user_id),
        service: QueensService = Depends(get_service),
    ) -> BoardResponse:
        return _build_board_response(service.get_board(user_id))

    @router.post("/add", response_model=MutationResponse)
    def add_endpoint(
        payload: QueenAddRequest,
        user_id: int = Depends(get_current_user_id),
        service: QueensService = Depends(get_service),
    ) -> MutationResponse | JSONResponse:
        try:
            if payload.queens is not None:
                total = service.add_queens(
                    user_id,
                    [QueenPosition(row=q.row, col=q.col) for q in payload.queens],
                )
            else:
                total = service.add_queen(user_id, payload.row, payload.col)  # type: ignore[arg-type]
            return MutationResponse(ok=True, total_queens=total)
        except OutOfBoundsError as exc:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "out_of_bounds", "message": str(exc)},
            )

    @router.post("/remove", response_model=MutationResponse)
    def remove_endpoint(
        payload: QueenMutationRequest,
        user_id: int = Depends(get_current_user_id),
        service: QueensService = Depends(get_service),
    ) -> MutationResponse | JSONResponse:
        try:
            return MutationResponse(ok=True, total_queens=service.remove_queen(user_id, payload.row, payload.col))
        except OutOfBoundsError as exc:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "out_of_bounds", "message": str(exc)},
            )

    @router.post("/submit", response_model=SubmitResponse, response_model_exclude_none=True)
    async def submit_endpoint(
        user_id: int = Depends(get_current_user_id),
        service: QueensService = Depends(get_service),
        gate: SubmissionGate = Depends(get_submission_gate),
    ) -> SubmitResponse | JSONResponse:
        try:
            async with gate.acquire(user_id, timeout=0.25):
                result = await run_in_threadpool(service.submit, user_id)
            return SubmitResponse(**asdict(result))
        except TooManySubmissionsError:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"error": "too_many_submissions", "message": "Too many submissions."},
            )
        except InvalidBoardError as exc:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"error": "invalid_board", "message": str(exc)},
            )

    @router.post("/reset", response_model=BoardResponse)
    def reset_endpoint(
        user_id: int = Depends(get_current_user_id),
        service: QueensService = Depends(get_service),
    ) -> BoardResponse:
        return _build_board_response(service.reset(user_id))

    return router

def _build_board_response(snapshot: BoardSnapshot) -> BoardResponse:
    return BoardResponse(
        size=snapshot.size,
        queens=[QueenPositionResponse(**asdict(queen)) for queen in snapshot.queens],
        total_queens=snapshot.total_queens,
        submission=SubmissionResponse(
            status=snapshot.submission.status,
            progress_pct=snapshot.submission.progress_pct,
            last_result=snapshot.submission.last_result,
            last_submitted_at=(
                snapshot.submission.last_submitted_at.isoformat()
                if snapshot.submission.last_submitted_at
                else None
            ),
        ),
    )
