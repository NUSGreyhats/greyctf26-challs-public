from __future__ import annotations

import time

from fastapi import FastAPI, Request

from app.observability.metrics import BackendMetrics, get_metrics

def instrument_fastapi_app(
    app: FastAPI,
    *,
    metrics: BackendMetrics | None = None,
) -> None:
    if getattr(app.state, "metrics_instrumented", False):
        return

    active_metrics = metrics or get_metrics()
    app.state.metrics_instrumented = True

    @app.middleware("http")
    async def observe_http_metrics(request: Request, call_next):
        active_metrics.increment_inprogress_requests()
        started_at = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            active_metrics.decrement_inprogress_requests()
            active_metrics.observe_http_request(
                method=request.method,
                route=_route_label(request),
                status_code=status_code,
                duration_seconds=time.perf_counter() - started_at,
            )

def _route_label(request: Request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str) and route_path:
        return route_path
    return "unmatched"

