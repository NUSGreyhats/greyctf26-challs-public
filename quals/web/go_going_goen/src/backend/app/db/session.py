from __future__ import annotations

from pathlib import Path
import time
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.core.config import settings
from app.core.team_context import BOOTSTRAP_TEAM_ID, get_team_id, get_team_id_required
from app.observability.metrics import get_metrics


class Database:
    def __init__(self, dsn: str | None = None, *, team_id: str | None = None) -> None:
        self._dsn = dsn or settings.database_url
        self._team_id = team_id
        self._connection: psycopg.Connection[dict[str, Any]] | None = None

    @classmethod
    def bootstrap(cls, dsn: str | None = None) -> "Database":
        return cls(dsn=dsn, team_id=BOOTSTRAP_TEAM_ID)

    @staticmethod
    def project_root() -> Path:
        path = Path(__file__).resolve()
        for candidate in path.parents:
            if (candidate / "src/backend/app/core/sql/shared_platform.sql").exists():
                return candidate
            if (candidate / "app/core/sql/shared_platform.sql").exists():
                return candidate
        raise RuntimeError("Could not resolve project root for SQL bootstrap files.")

    @staticmethod
    def configure_connection(
        connection: psycopg.Connection[dict[str, Any]],
        team_id: str,
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.team_id', %s, false)",
                [team_id],
            )
            cursor.execute("SET row_security = on")

    def _resolve_team_id(self) -> str:
        if self._team_id is not None:
            return self._team_id
        return get_team_id_required()

    def __enter__(self) -> "Database":
        started_at = time.perf_counter()
        self._connection = psycopg.connect(
            self._dsn,
            row_factory=dict_row,
            autocommit=False,
            prepare_threshold=None,
        )
        self.configure_connection(self._connection, self._resolve_team_id())
        metrics = get_metrics()
        metrics.observe_connection_open(time.perf_counter() - started_at)
        metrics.increment_checked_out_connections()
        return self

    def __exit__(self, exc_type, exc, _tb) -> None:
        if self._connection is None:
            return
        if exc_type is None:
            self._connection.commit()
        else:
            self._connection.rollback()
        self._connection.close()
        self._connection = None
        get_metrics().decrement_checked_out_connections()

    @property
    def connection(self) -> psycopg.Connection[dict[str, Any]]:
        if self._connection is None:
            raise RuntimeError("Database connection is not open.")
        return self._connection

    def commit(self) -> None:
        connection = self.connection
        connection.commit()
        self.configure_connection(connection, self._resolve_team_id())

    def fetch_one(self, query: str, params: list[Any]) -> dict[str, Any] | None:
        started_at = time.perf_counter()
        failed = False
        with self.connection.cursor() as cursor:
            try:
                cursor.execute(query, params)
                return cursor.fetchone()
            except Exception:
                failed = True
                raise
            finally:
                get_metrics().observe_db_query(
                    operation="fetch_one",
                    query=query,
                    duration_seconds=time.perf_counter() - started_at,
                    failed=failed,
                )

    def fetch_all(self, query: str, params: list[Any]) -> list[dict[str, Any]]:
        started_at = time.perf_counter()
        failed = False
        with self.connection.cursor() as cursor:
            try:
                cursor.execute(query, params)
                return list(cursor.fetchall())
            except Exception:
                failed = True
                raise
            finally:
                get_metrics().observe_db_query(
                    operation="fetch_all",
                    query=query,
                    duration_seconds=time.perf_counter() - started_at,
                    failed=failed,
                )

    def fetch_val(self, query: str, params: list[Any]) -> Any:
        row = self.fetch_one(query, params)
        if row is None:
            return None
        return next(iter(row.values()))

    def execute(self, query: str, params: list[Any]) -> dict[str, Any] | None:
        started_at = time.perf_counter()
        failed = False
        with self.connection.cursor() as cursor:
            try:
                cursor.execute(query, params)
                if cursor.description is None:
                    return None
                return cursor.fetchone()
            except Exception:
                failed = True
                raise
            finally:
                get_metrics().observe_db_query(
                    operation="execute",
                    query=query,
                    duration_seconds=time.perf_counter() - started_at,
                    failed=failed,
                )

    def execute_script(self, sql: str) -> None:
        started_at = time.perf_counter()
        failed = False
        with self.connection.cursor() as cursor:
            try:
                cursor.execute(sql)
            except Exception:
                failed = True
                raise
            finally:
                get_metrics().observe_db_query(
                    operation="execute_script",
                    query=sql,
                    duration_seconds=time.perf_counter() - started_at,
                    failed=failed,
                )

