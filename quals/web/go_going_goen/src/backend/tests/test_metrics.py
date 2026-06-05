from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry

from app.api.routes.health import router as health_router
from app.db.session import Database
from app.observability.http import instrument_fastapi_app
from app.observability.metrics import BackendMetrics, override_metrics_for_testing


class _FakeCursor:
    def __init__(self, *, fail: bool) -> None:
        self._fail = fail
        self.description = [("value",)]

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, _query: str, _params: list[object] | None = None) -> None:
        if self._fail:
            raise RuntimeError("boom")

    def fetchone(self) -> dict[str, int]:
        return {"value": 1}

    def fetchall(self) -> list[dict[str, int]]:
        return [{"value": 1}]


class _FakeConnection:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.commits = 0

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(fail=self._fail)

    def commit(self) -> None:
        self.commits += 1


def _client_with_token(monkeypatch: pytest.MonkeyPatch, token: str | None) -> TestClient:
    from app.core import config as config_module

    monkeypatch.setattr(config_module.settings, "metrics_token", token)
    app = FastAPI()
    app.include_router(health_router)
    return TestClient(app)


def test_metrics_endpoint_exposes_prometheus_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client_with_token(monkeypatch, "test-token")
    response = client.get("/metrics", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "http_requests_total" in response.text
    assert "db_queries_total" in response.text
    assert "stage_gate_wait_seconds" in response.text
    assert "stage_submit_duration_seconds" in response.text


def test_metrics_endpoint_returns_503_when_token_cleared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client_with_token(monkeypatch, "")
    monkeypatch.setattr("app.core.config.settings.metrics_token", None)
    response = client.get("/metrics")
    assert response.status_code == 503
    body = response.json()["detail"]
    assert body["error"] == "metrics_disabled"


def test_metrics_endpoint_requires_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client_with_token(monkeypatch, "real-token")

    no_header = client.get("/metrics")
    wrong_token = client.get("/metrics", headers={"Authorization": "Bearer wrong"})
    wrong_scheme = client.get("/metrics", headers={"Authorization": "Basic real-token"})

    for response in (no_header, wrong_token, wrong_scheme):
        assert response.status_code == 401, response.text
        assert response.headers.get("WWW-Authenticate", "").lower().startswith("bearer")


def test_http_middleware_records_request_metrics() -> None:
    metrics = BackendMetrics(
        registry=CollectorRegistry(auto_describe=True),
        include_runtime_collectors=False,
    )
    app = FastAPI()
    instrument_fastapi_app(app, metrics=metrics)

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    client = TestClient(app)
    response = client.get("/ping")
    body = metrics.render().decode()

    assert response.status_code == 200
    assert 'http_requests_total{method="GET",route="/ping",status_class="2xx"} 1.0' in body
    assert "http_inprogress_requests 0.0" in body


def test_database_wrapper_records_query_metrics() -> None:
    metrics = BackendMetrics(
        registry=CollectorRegistry(auto_describe=True),
        include_runtime_collectors=False,
    )
    db = Database(dsn="postgresql://example")

    with override_metrics_for_testing(metrics):
        db._connection = _FakeConnection(fail=False)
        assert db.fetch_one("SELECT 1", []) == {"value": 1}

        db._connection = _FakeConnection(fail=True)
        with pytest.raises(RuntimeError):
            db.execute("UPDATE users SET active = false", [])

        body = metrics.render().decode()

    assert 'db_queries_total{operation="fetch_one",statement="SELECT"} 1.0' in body
    assert 'db_query_errors_total{operation="execute",statement="UPDATE"} 1.0' in body


def test_database_commit_reconfigures_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    db = Database(dsn="postgresql://example", team_id="test-team")
    connection = _FakeConnection()
    db._connection = connection
    calls = 0

    def configure(_connection: _FakeConnection, _team_id: str) -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(Database, "configure_connection", staticmethod(configure))

    db.commit()

    assert connection.commits == 1
    assert calls == 1
