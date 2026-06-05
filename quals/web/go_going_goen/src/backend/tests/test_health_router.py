import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import health
from app.api.routes.health import router, settings


def _make_client(monkeypatch, fake_ping) -> TestClient:
    monkeypatch.setattr(
        settings,
        "database_url",
        "postgresql://user:secret@127.0.0.1:6432/go_going_goen",
    )
    monkeypatch.setattr(health, "_ping_db_sync", fake_ping)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_healthcheck_db_ok(monkeypatch) -> None:
    client = _make_client(monkeypatch, lambda: None)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "db": "ok",
        "database_endpoint": "127.0.0.1:6432/go_going_goen",
    }


def test_healthcheck_db_timeout(monkeypatch) -> None:
    def slow() -> None:
        import time
        time.sleep(5.0)

    client = _make_client(monkeypatch, slow)
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["db"] == "timeout"


def test_healthcheck_db_error(monkeypatch) -> None:
    def boom() -> None:
        raise RuntimeError("simulated")

    client = _make_client(monkeypatch, boom)
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["db"] == "RuntimeError"
