from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.routes.admin import router as admin_router
from app.core.config import settings
from app.core.exceptions import AppError


def _admin_client(monkeypatch, *, admin_token: str | None) -> TestClient:
    monkeypatch.setattr(settings, "admin_token", admin_token)
    app = FastAPI()
    app.include_router(admin_router, prefix="/api")

    @app.exception_handler(AppError)
    def handle_app_error(_request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error, "message": exc.message},
        )

    return TestClient(app)


def test_admin_health_detail_requires_token(monkeypatch) -> None:
    client = _admin_client(monkeypatch, admin_token="secret-admin")

    response = client.get("/api/admin/health-detail")

    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_admin_health_detail_accepts_bearer_token(monkeypatch) -> None:
    client = _admin_client(monkeypatch, admin_token="secret-admin")

    class FakeDb:
        def fetch_val(self, query: str, params: list[object]) -> int:
            del query, params
            return 0

    @contextmanager
    def fake_bootstrap():
        yield FakeDb()

    with patch("app.api.routes.admin.Database.bootstrap", fake_bootstrap):
        response = client.get(
            "/api/admin/health-detail",
            headers={"Authorization": "Bearer secret-admin"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "database_endpoint" in body
    assert "auth_mode" not in body


def test_admin_reset_all_requires_token(monkeypatch) -> None:
    client = _admin_client(monkeypatch, admin_token="secret-admin")

    response = client.post("/api/admin/reset-all")

    assert response.status_code == 401


def test_admin_disabled_when_token_unset(monkeypatch) -> None:
    client = _admin_client(monkeypatch, admin_token=None)

    response = client.get(
        "/api/admin/health-detail",
        headers={"Authorization": "Bearer anything"},
    )

    assert response.status_code == 503
    assert response.json()["error"] == "admin_disabled"
