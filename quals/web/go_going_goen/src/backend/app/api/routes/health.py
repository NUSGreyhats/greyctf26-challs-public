from __future__ import annotations

import asyncio
import hmac

import psycopg
from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import Response

from app.core.config import settings
from app.observability.metrics import metrics_content_type, render_metrics

router = APIRouter()

_HEALTHZ_DB_TIMEOUT_SECONDS = 1.0


def _ping_db_sync() -> None:
    # asyncio.wait_for() in healthcheck() bounds the wall-clock; psycopg's
    # connect_timeout backstops the TCP dial. We deliberately don't pass
    # `options=...` because pgbouncer rejects unknown startup parameters by
    # default (FATAL "unsupported startup parameter in options"), which
    # would itself become a false-positive DB-down signal.
    with psycopg.connect(
        settings.database_url,
        connect_timeout=int(_HEALTHZ_DB_TIMEOUT_SECONDS),
        autocommit=True,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()


@router.get("/healthz")
async def healthcheck() -> dict[str, str]:
    base = {"database_endpoint": settings.database_endpoint}
    try:
        await asyncio.wait_for(
            asyncio.to_thread(_ping_db_sync),
            timeout=_HEALTHZ_DB_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return {"status": "degraded", "db": "timeout", **base}
    except psycopg.OperationalError as exc:
        return {"status": "degraded", "db": "operational_error", "detail": str(exc)[:120], **base}
    except Exception as exc:
        return {"status": "degraded", "db": type(exc).__name__, **base}
    return {"status": "ok", "db": "ok", **base}

@router.get("/metrics", include_in_schema=False)
def metrics(authorization: str | None = Header(default=None)) -> Response:
    token = settings.metrics_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "metrics_disabled",
                "message": "Set METRICS_TOKEN in the server environment to expose /metrics.",
            },
        )

    provided = _extract_bearer(authorization)
    if provided is None or not hmac.compare_digest(provided, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": 'Bearer realm="metrics"'},
            detail={
                "error": "metrics_unauthorized",
                "message": "Provide `Authorization: Bearer <METRICS_TOKEN>`.",
            },
        )

    return Response(content=render_metrics(), media_type=metrics_content_type())

def _extract_bearer(header_value: str | None) -> str | None:
    if not header_value:
        return None
    scheme, _, credentials = header_value.partition(" ")
    if scheme.lower() != "bearer" or not credentials:
        return None
    return credentials.strip()
