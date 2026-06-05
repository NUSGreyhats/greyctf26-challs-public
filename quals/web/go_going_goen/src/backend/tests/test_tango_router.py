from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import AppError
from app.stages.stage3.repository import INITIAL_GRID, SOLUTION_GRID
from app.stages.stage3.router import create_tango_router
from app.stages.stage3.service import SubmissionGate, TangoService
from app.stages.stage3.testing import InMemoryTangoRepository

from .test_tango_service import FINAL_FLAG, ProgressGatewayStub


def build_client() -> tuple[TestClient, TangoService, InMemoryTangoRepository]:
    repository = InMemoryTangoRepository()
    service = TangoService(
        repository=repository,
        progress_gateway=ProgressGatewayStub(),
        final_flag=FINAL_FLAG,
    )
    app = FastAPI()

    @app.exception_handler(AppError)
    def handle_app_error(_request, exc: AppError):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error, "message": exc.message},
        )

    app.include_router(
        create_tango_router(
            get_service=lambda: service,
            get_current_user_id=lambda: 41,
            get_submission_gate=lambda: SubmissionGate(capacity=2),
        )
    )
    return TestClient(app), service, repository


def build_locked_client() -> TestClient:
    repository = InMemoryTangoRepository()
    service = TangoService(
        repository=repository,
        progress_gateway=ProgressGatewayStub(),
        final_flag=FINAL_FLAG,
    )
    app = FastAPI()

    @app.exception_handler(AppError)
    def handle_app_error(_request, exc: AppError):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error, "message": exc.message},
        )

    def locked_user_id() -> int:
        raise AppError(
            status_code=403,
            error="stage_locked",
            message="Stage 3 is locked until Stage 2 is cleared.",
        )

    app.include_router(
        create_tango_router(
            get_service=lambda: service,
            get_current_user_id=locked_user_id,
            get_submission_gate=lambda: SubmissionGate(capacity=2),
        )
    )
    return TestClient(app)


def test_status_endpoint_returns_tango_puzzle_and_ledger() -> None:
    client, _, _ = build_client()

    response = client.get("/api/v3/tango/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["puzzle"]["size"] == 6
    assert payload["puzzle"]["values"] == {"empty": 0, "sun": 1, "moon": 2}
    assert payload["puzzle"]["initial_grid"] == INITIAL_GRID
    assert payload["ledger"]["currency_symbol"] == "$"
    assert payload["ledger"]["spendable_dollars"] == 0
    assert payload["ledger"]["play_cost_dollars"] == 100
    assert payload["ledger"]["flag_cost_dollars"] == 1000
    assert payload["latest_attempt_state"] == "idle"


def test_submit_endpoint_rejects_string_cells_before_service() -> None:
    client, _, _ = build_client()

    response = client.post("/api/v3/tango/submit", json={"grid": [["SUN"]]})

    assert response.status_code == 422


def test_submit_endpoint_rejects_out_of_range_integer_cells() -> None:
    client, _, _ = build_client()
    bad_grid = [list(row) for row in SOLUTION_GRID]
    bad_grid[0][0] = 9

    response = client.post("/api/v3/tango/submit", json={"grid": bad_grid})

    assert response.status_code == 422


def test_submit_endpoint_accepts_valid_solution() -> None:
    client, _, _ = build_client()

    response = client.post("/api/v3/tango/submit", json={"grid": SOLUTION_GRID})

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"] == "accepted"
    assert payload["dollars_awarded"] == 100
    assert isinstance(payload["attempt_id"], str)


def test_submit_endpoint_returns_invalid_grid_with_attempt_id() -> None:
    client, _, _ = build_client()
    invalid_grid = [list(row) for row in SOLUTION_GRID]
    invalid_grid[0][0] = 2

    response = client.post("/api/v3/tango/submit", json={"grid": invalid_grid})

    payload = response.json()
    assert response.status_code == 400
    assert payload["error"] == "invalid_grid"
    assert payload["message"] == "Grid rejected."
    assert isinstance(payload["attempt_id"], str)


def test_submit_endpoint_returns_generic_validation_error() -> None:
    client, _, repository = build_client()
    repository.raise_validation_database_error = True

    response = client.post("/api/v3/tango/submit", json={"grid": SOLUTION_GRID})

    payload = response.json()
    assert response.status_code == 500
    assert payload["error"] == "validation_error"
    assert payload["message"] == "Validation could not complete."
    assert isinstance(payload["attempt_id"], str)


def test_ledger_and_attempt_endpoints_expose_pending_credit() -> None:
    client, _, repository = build_client()
    repository.raise_validation_database_error = True
    submit = client.post("/api/v3/tango/submit", json={"grid": SOLUTION_GRID})
    attempt_id = submit.json()["attempt_id"]

    ledger_response = client.get("/api/v3/tango/ledger")
    attempt_response = client.get(f"/api/v3/tango/attempt/{attempt_id}")

    assert ledger_response.status_code == 200
    assert ledger_response.json()["pending_dollars"] == 100
    assert ledger_response.json()["spendable_dollars"] == 100
    assert attempt_response.status_code == 200
    attempt_body = attempt_response.json()
    assert attempt_body["attempt_id"] == attempt_id
    assert attempt_body["status"] == "crashed"
    assert attempt_body["ledger_status"] == "PENDING"
    assert set(attempt_body["lock_order"]) == {f"row_balance:{i}" for i in range(1, 7)}


def test_refresh_ledger_endpoint_reconciles_pending_credit_to_zero() -> None:
    client, _, repository = build_client()
    repository.raise_validation_database_error = True
    client.post("/api/v3/tango/submit", json={"grid": SOLUTION_GRID})

    response = client.post("/api/v3/tango/ledger/refresh")

    assert response.status_code == 200
    assert response.json()["pending_dollars"] == 0
    assert response.json()["spendable_dollars"] == 0
    assert response.json()["entries"][0]["status"] == "ROLLED_BACK"


def test_buy_flag_endpoint_requires_ten_pending_credits_then_returns_flag() -> None:
    client, _, repository = build_client()

    not_enough = client.post("/api/v3/tango/buy-flag")
    assert not_enough.status_code == 402
    assert not_enough.json() == {"error": "not_enough_credits", "message": "Not enough credits."}

    for _ in range(10):
        repository.raise_validation_database_error = True
        client.post("/api/v3/tango/submit", json={"grid": SOLUTION_GRID})

    response = client.post("/api/v3/tango/buy-flag")

    assert response.status_code == 200
    assert response.json() == {"result": "win", "flag": FINAL_FLAG}


def test_attempt_endpoint_returns_not_found_shape() -> None:
    client, _, _ = build_client()

    response = client.get("/api/v3/tango/attempt/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json() == {
        "error": "attempt_not_found",
        "message": "Attempt not found.",
    }


def test_reset_endpoint_clears_tango_state() -> None:
    client, _, _ = build_client()
    client.post("/api/v3/tango/submit", json={"grid": SOLUTION_GRID})

    response = client.post("/api/v3/tango/reset")

    assert response.status_code == 200
    assert response.json()["puzzle"]["initial_grid"] == INITIAL_GRID
    assert response.json()["ledger"]["entries"] == []


def test_status_endpoint_returns_locked_error_when_stage3_is_not_unlocked() -> None:
    client = build_locked_client()

    response = client.get("/api/v3/tango/status")

    assert response.status_code == 403
    assert response.json() == {
        "error": "stage_locked",
        "message": "Stage 3 is locked until Stage 2 is cleared.",
    }
