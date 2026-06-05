from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.exceptions import AppError
from app.stages.stage2.router import create_queens_router
from app.stages.stage2.service import (
    QueensService,
    SubmissionGate,
    TooManySubmissionsError,
)
from app.stages.stage2.testing import InMemoryBoardStore, InMemorySubmissionStore

from .test_queens_service import FixedClock, ProgressGatewayStub


def build_client(
    board_store: InMemoryBoardStore | None = None,
) -> tuple[
    TestClient, InMemoryBoardStore, InMemorySubmissionStore, ProgressGatewayStub
]:
    board = board_store or InMemoryBoardStore()
    submissions = InMemorySubmissionStore()
    progress = ProgressGatewayStub()
    service = QueensService(
        board_store=board,
        submission_store=submissions,
        progress_store=progress,
        clock=FixedClock(datetime(2026, 5, 12, tzinfo=UTC)),
    )
    service.reset(41)

    app = FastAPI()
    app.include_router(
        create_queens_router(
            get_service=lambda: service,
            get_current_user_id=lambda: 41,
            get_submission_gate=lambda: SubmissionGate(capacity=4),
        )
    )

    @app.exception_handler(AppError)
    def handle_app_error(_request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error, "message": exc.message},
        )

    return TestClient(app), board, submissions, progress


def build_locked_client() -> TestClient:
    board = InMemoryBoardStore()
    submissions = InMemorySubmissionStore()
    progress = ProgressGatewayStub()
    service = QueensService(
        board_store=board,
        submission_store=submissions,
        progress_store=progress,
        clock=FixedClock(datetime(2026, 5, 12, tzinfo=UTC)),
    )

    app = FastAPI()

    @app.exception_handler(AppError)
    def handle_app_error(_request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error, "message": exc.message},
        )

    def locked_user_id() -> int:
        raise AppError(
            status_code=403,
            error="stage_locked",
            message="Stage 2 is locked until Stage 1 is cleared.",
        )

    app.include_router(
        create_queens_router(
            get_service=lambda: service,
            get_current_user_id=locked_user_id,
            get_submission_gate=lambda: SubmissionGate(capacity=4),
        )
    )
    return TestClient(app)


class BusySubmissionGate:
    @asynccontextmanager
    async def acquire(self, _user_id: int, timeout: float = 0.25):
        raise TooManySubmissionsError()
        yield


def test_board_endpoint_returns_default_snapshot() -> None:
    client, _, _, _ = build_client()

    response = client.get("/api/v2/queens/board")

    payload = response.json()
    assert response.status_code == 200
    assert payload["size"] == 50
    assert payload["total_queens"] == 0
    assert payload["submission"]["status"] == "idle"


def test_add_endpoint_returns_updated_total() -> None:
    client, _, _, _ = build_client()

    response = client.post("/api/v2/queens/add", json={"row": 0, "col": 1})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "total_queens": 1}


def test_add_endpoint_does_not_duplicate_occupied_square() -> None:
    client, _, _, _ = build_client()

    client.post("/api/v2/queens/add", json={"row": 0, "col": 1})
    response = client.post("/api/v2/queens/add", json={"row": 0, "col": 1})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "total_queens": 1}


def test_add_endpoint_accepts_array_form() -> None:
    client, _, _, _ = build_client()

    response = client.post(
        "/api/v2/queens/add",
        json={
            "queens": [
                {"row": 0, "col": 1},
                {"row": 1, "col": 2},
                {"row": 0, "col": 1},
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "total_queens": 2}


def test_add_endpoint_rejects_array_over_cap() -> None:
    client, _, _, _ = build_client()
    too_many = [{"row": r // 50, "col": r % 50} for r in range(51)]

    response = client.post("/api/v2/queens/add", json={"queens": too_many})

    assert response.status_code == 422


def test_add_endpoint_rejects_both_shapes() -> None:
    client, _, _, _ = build_client()

    response = client.post(
        "/api/v2/queens/add",
        json={"row": 0, "col": 1, "queens": [{"row": 2, "col": 2}]},
    )

    assert response.status_code == 422


def test_add_endpoint_rejects_empty_payload() -> None:
    client, _, _, _ = build_client()

    response = client.post("/api/v2/queens/add", json={})

    assert response.status_code == 422


def test_remove_endpoint_rejects_out_of_bounds_positions() -> None:
    client, _, _, _ = build_client()

    response = client.post("/api/v2/queens/remove", json={"row": 50, "col": 0})

    assert response.status_code == 400
    assert response.json() == {
        "error": "out_of_bounds",
        "message": "Queen position is outside the board.",
    }


def test_submit_endpoint_returns_invalid_board_shape() -> None:
    client, board, _, _ = build_client()
    board.insert_queen(41, 0, 0)
    board.insert_queen(41, 0, 1)

    response = client.post("/api/v2/queens/submit")

    assert response.status_code == 409
    assert response.json() == {
        "error": "invalid_board",
        "message": "Board failed validation.",
    }


def test_submit_endpoint_returns_too_many_submissions_shape() -> None:
    board = InMemoryBoardStore()
    submissions = InMemorySubmissionStore()
    progress = ProgressGatewayStub()
    service = QueensService(
        board_store=board,
        submission_store=submissions,
        progress_store=progress,
        clock=FixedClock(datetime(2026, 5, 12, tzinfo=UTC)),
    )
    service.reset(41)

    app = FastAPI()
    app.include_router(
        create_queens_router(
            get_service=lambda: service,
            get_current_user_id=lambda: 41,
            get_submission_gate=lambda: BusySubmissionGate(),
        )
    )

    response = TestClient(app).post("/api/v2/queens/submit")

    assert response.status_code == 429
    assert response.json() == {
        "error": "too_many_submissions",
        "message": "Too many submissions.",
    }


def test_reset_endpoint_restores_empty_snapshot() -> None:
    client, _, _, _ = build_client()
    client.post("/api/v2/queens/add", json={"row": 0, "col": 1})

    response = client.post("/api/v2/queens/reset")

    assert response.status_code == 200
    assert response.json() == {
        "size": 50,
        "queens": [],
        "total_queens": 0,
        "submission": {
            "status": "idle",
            "progress_pct": 0,
            "last_result": None,
            "last_submitted_at": None,
        },
    }


def test_board_endpoint_returns_locked_error_when_stage2_is_not_unlocked() -> None:
    client = build_locked_client()

    response = client.get("/api/v2/queens/board")

    assert response.status_code == 403
    assert response.json() == {
        "error": "stage_locked",
        "message": "Stage 2 is locked until Stage 1 is cleared.",
    }
