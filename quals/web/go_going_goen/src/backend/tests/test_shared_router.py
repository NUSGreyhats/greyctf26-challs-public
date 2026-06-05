from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.routes import auth as auth_routes
from app.api.routes.auth import router as auth_router
from app.api.routes.shared import router as shared_router
from app.core.exceptions import AppError
from app.models.auth import SessionUser


def test_auth_session_sets_cookie(monkeypatch) -> None:
    monkeypatch.setattr(
        auth_routes,
        "create_session_from_token",
        lambda _token: (SessionUser(user_id=1, username="team", team_id="abc"), "sess-1"),
    )

    app = FastAPI()
    app.include_router(auth_router, prefix="/api")

    @app.exception_handler(AppError)
    def handle_app_error(_request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error, "message": exc.message},
        )

    client = TestClient(app)

    response = client.post("/api/auth/session?token=tt_dev_fixed")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "authenticated": True}
    assert "ggg_session=" in response.headers["set-cookie"]


def test_auth_session_accepts_json_body(monkeypatch) -> None:
    monkeypatch.setattr(
        auth_routes,
        "create_session_from_token",
        lambda _token: (SessionUser(user_id=1, username="team", team_id="abc"), "sess-1"),
    )

    app = FastAPI()
    app.include_router(auth_router, prefix="/api")

    @app.exception_handler(AppError)
    def handle_app_error(_request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error, "message": exc.message},
        )

    client = TestClient(app)

    response = client.post(
        "/api/auth/session",
        json={"token": "tt_dev_fixed"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "authenticated": True}
    assert "ggg_session=" in response.headers["set-cookie"]


def test_me_without_session_returns_unauthenticated() -> None:
    app = FastAPI()
    app.include_router(shared_router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/me")

    assert response.status_code == 200
    assert response.json() == {"user_id": None, "username": None}
    assert "ggg_session" not in response.headers.get("set-cookie", "")
