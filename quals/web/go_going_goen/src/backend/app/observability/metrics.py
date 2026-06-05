from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Iterator

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    GCCollector,
    PLATFORM_COLLECTOR,
    PROCESS_COLLECTOR,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    PlatformCollector,
    ProcessCollector,
    REGISTRY,
    generate_latest,
)

KNOWN_SQL_STATEMENTS = {
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "CREATE",
    "ALTER",
    "DROP",
    "WITH",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "SET",
    "SHOW",
    "BEGIN",
    "COMMIT",
    "ROLLBACK",
}

HTTP_LATENCY_BUCKETS = (
    0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
)
DB_LATENCY_BUCKETS = (
    0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5,
)
GATE_WAIT_BUCKETS = (
    0.0001, 0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5,
)
STAGE_SUBMIT_BUCKETS = (
    0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0,
)
DB_CONNECTION_OPEN_BUCKETS = (
    0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5,
)

class BackendMetrics:
    def __init__(
        self,
        *,
        registry: CollectorRegistry | None = None,
        include_runtime_collectors: bool = True,
        slow_query_threshold_seconds: float = 0.1,
    ) -> None:
        self._registry = registry or REGISTRY
        self._slow_query_threshold = slow_query_threshold_seconds
        if include_runtime_collectors:
            self._register_runtime_collectors()

        self.http_requests_total = Counter(
            "http_requests_total",
            "Total HTTP requests handled by route.",
            ["method", "route", "status_class"],
            registry=self._registry,
        )
        self.http_request_duration_seconds = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency by route.",
            ["method", "route"],
            buckets=HTTP_LATENCY_BUCKETS,
            registry=self._registry,
        )
        self.http_inprogress_requests = Gauge(
            "http_inprogress_requests",
            "Number of in-flight HTTP requests.",
            registry=self._registry,
        )
        self.http_response_bytes = Histogram(
            "http_response_bytes",
            "HTTP response body size by route (bytes).",
            ["method", "route"],
            buckets=(64, 256, 1024, 4096, 16384, 65536, 262144, 1048576),
            registry=self._registry,
        )

        self.db_queries_total = Counter(
            "db_queries_total",
            "Total DB queries executed by operation and statement type.",
            ["operation", "statement"],
            registry=self._registry,
        )
        self.db_query_duration_seconds = Histogram(
            "db_query_duration_seconds",
            "DB query duration by operation and statement type.",
            ["operation", "statement"],
            buckets=DB_LATENCY_BUCKETS,
            registry=self._registry,
        )
        self.db_query_errors_total = Counter(
            "db_query_errors_total",
            "Total DB query failures by operation and statement type.",
            ["operation", "statement"],
            registry=self._registry,
        )
        self.db_slow_queries_total = Counter(
            "db_slow_queries_total",
            "Total DB queries exceeding the slow-query threshold.",
            ["operation", "statement"],
            registry=self._registry,
        )
        self.db_pool_checked_out = Gauge(
            "db_pool_checked_out",
            "Current number of open DB connections in this process.",
            registry=self._registry,
        )
        self.db_connection_open_seconds = Histogram(
            "db_connection_open_seconds",
            "Time spent opening and configuring a DB connection.",
            buckets=DB_CONNECTION_OPEN_BUCKETS,
            registry=self._registry,
        )

        self.stage_gate_wait_seconds = Histogram(
            "stage_gate_wait_seconds",
            "Time spent waiting on a per-stage submission/guess gate.",
            ["stage", "outcome"],
            buckets=GATE_WAIT_BUCKETS,
            registry=self._registry,
        )
        self.stage_submit_duration_seconds = Histogram(
            "stage_submit_duration_seconds",
            "End-to-end duration of a stage submit/guess call.",
            ["stage", "outcome"],
            buckets=STAGE_SUBMIT_BUCKETS,
            registry=self._registry,
        )

    def _register_runtime_collectors(self) -> None:
        collectors = (
            (PROCESS_COLLECTOR, ProcessCollector),
            (PLATFORM_COLLECTOR, PlatformCollector),
            (GCCollector, GCCollector),
        )
        for collector, constructor in collectors:
            try:
                constructor(registry=self._registry)
            except ValueError:
                continue

    def observe_http_request(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
        response_bytes: int | None = None,
    ) -> None:
        method_label = method.upper()
        route_label = route or "unmatched"
        status_class = f"{status_code // 100}xx"
        self.http_requests_total.labels(
            method=method_label,
            route=route_label,
            status_class=status_class,
        ).inc()
        self.http_request_duration_seconds.labels(
            method=method_label,
            route=route_label,
        ).observe(duration_seconds)
        if response_bytes is not None:
            self.http_response_bytes.labels(
                method=method_label,
                route=route_label,
            ).observe(response_bytes)

    def increment_inprogress_requests(self) -> None:
        self.http_inprogress_requests.inc()

    def decrement_inprogress_requests(self) -> None:
        self.http_inprogress_requests.dec()

    def observe_db_query(
        self,
        *,
        operation: str,
        query: str,
        duration_seconds: float,
        failed: bool,
    ) -> None:
        statement = statement_type(query)
        operation_label = operation.lower()
        self.db_queries_total.labels(
            operation=operation_label,
            statement=statement,
        ).inc()
        self.db_query_duration_seconds.labels(
            operation=operation_label,
            statement=statement,
        ).observe(duration_seconds)
        if failed:
            self.db_query_errors_total.labels(
                operation=operation_label,
                statement=statement,
            ).inc()
        if duration_seconds >= self._slow_query_threshold:
            self.db_slow_queries_total.labels(
                operation=operation_label,
                statement=statement,
            ).inc()

    def increment_checked_out_connections(self) -> None:
        self.db_pool_checked_out.inc()

    def decrement_checked_out_connections(self) -> None:
        self.db_pool_checked_out.dec()

    def observe_connection_open(self, duration_seconds: float) -> None:
        self.db_connection_open_seconds.observe(duration_seconds)

    def observe_gate_wait(
        self,
        *,
        stage: str,
        outcome: str,
        duration_seconds: float,
    ) -> None:
        self.stage_gate_wait_seconds.labels(
            stage=stage,
            outcome=outcome,
        ).observe(duration_seconds)

    def observe_stage_submit(
        self,
        *,
        stage: str,
        outcome: str,
        duration_seconds: float,
    ) -> None:
        self.stage_submit_duration_seconds.labels(
            stage=stage,
            outcome=outcome,
        ).observe(duration_seconds)

    def render(self) -> bytes:
        return generate_latest(self._registry)

    @property
    def content_type(self) -> str:
        return CONTENT_TYPE_LATEST

def statement_type(query: str) -> str:
    tokens = re.findall(r"[A-Za-z]+", query or "")
    if not tokens:
        return "UNKNOWN"
    upper_tokens = [token.upper() for token in tokens]

    for verb in ("UPDATE", "INSERT", "DELETE", "MERGE"):
        if verb in upper_tokens:
            return verb

    head = upper_tokens[0]
    if head in KNOWN_SQL_STATEMENTS:
        return head
    return "OTHER"

def _build_default_metrics() -> BackendMetrics:
    from app.core.config import settings

    return BackendMetrics(
        slow_query_threshold_seconds=settings.db_slow_query_seconds,
    )

_DEFAULT_METRICS = _build_default_metrics()
_ACTIVE_METRICS = _DEFAULT_METRICS

def get_metrics() -> BackendMetrics:
    return _ACTIVE_METRICS

@contextmanager
def override_metrics_for_testing(metrics: BackendMetrics) -> Iterator[None]:
    global _ACTIVE_METRICS
    previous = _ACTIVE_METRICS
    _ACTIVE_METRICS = metrics
    try:
        yield
    finally:
        _ACTIVE_METRICS = previous

def render_metrics() -> bytes:
    return get_metrics().render()

def metrics_content_type() -> str:
    return get_metrics().content_type
