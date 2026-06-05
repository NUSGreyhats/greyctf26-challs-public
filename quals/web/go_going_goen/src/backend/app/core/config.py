import hashlib
import os
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field

DEFAULT_METRICS_TOKEN = (
    "58a3e3e137d8117321b04138b3d4d9d7f27c8503a2ba2fba625c0510b065d563"
)


def derive_internal_team_id(
    *,
    team_id_salt: str,
    ctfd_challenge_id: int,
    ctfd_team_id: int,
) -> str:
    material = f"{team_id_salt}:{ctfd_challenge_id}:{ctfd_team_id}".encode()
    return hashlib.sha256(material).hexdigest()


class Settings(BaseModel):
    app_name: str = "Go Going Goen"
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@db:5432/go_going_goen",
    ).replace("postgresql+psycopg://", "postgresql://")
    database_admin_url: str | None = Field(
        default_factory=lambda: (
            os.getenv("DATABASE_ADMIN_URL", "").replace("postgresql+psycopg://", "postgresql://")
            or None
        )
    )
    session_secret: str = os.getenv("SESSION_SECRET", "replace-me")
    pinpoint_secret: str = Field(
        default_factory=lambda: os.getenv("PINPOINT_SECRET", "replace-me-pinpoint")
    )
    singleton_username: str = os.getenv("SINGLETON_USERNAME", "team")
    team_id_salt: str = os.getenv("TEAM_ID_SALT", "replace-me")
    flag: str = Field(
        default_factory=lambda: os.getenv("FLAG", "grey{placeholder_flag}")
    )
    ctfd_resolve_url: str = os.getenv("CTFD_RESOLVE_URL", "")
    ctfd_team_token_plugin_secret: str = os.getenv("CTFD_TEAM_TOKEN_PLUGIN_SECRET", "")
    ctfd_challenge_id: int | None = Field(
        default_factory=lambda: (
            int(os.environ["CTFD_CHALLENGE_ID"])
            if os.getenv("CTFD_CHALLENGE_ID")
            else None
        )
    )
    admin_token: str | None = os.getenv("ADMIN_TOKEN") or None
    session_ttl_days: int = int(os.getenv("SESSION_TTL_DAYS", "7"))
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    app_static_dir: Path = Path(os.getenv("APP_STATIC_DIR", "/app/static"))
    metrics_token: str | None = os.getenv("METRICS_TOKEN") or DEFAULT_METRICS_TOKEN
    db_slow_query_seconds: float = float(os.getenv("DB_SLOW_QUERY_SECONDS", "0.1"))
    pinpoint_diagnostics_target_ms: float = Field(
        default_factory=lambda: float(os.getenv("PINPOINT_DIAGNOSTICS_TARGET_MS", "15"))
    )
    pinpoint_diagnostics_attest_rounds: int | None = Field(
        default_factory=lambda: (
            int(os.environ["PINPOINT_DIAGNOSTICS_ATTEST_ROUNDS"])
            if os.getenv("PINPOINT_DIAGNOSTICS_ATTEST_ROUNDS")
            else None
        )
    )

    @property
    def database_endpoint(self) -> str:
        parsed = urlparse(self.database_url)
        host = parsed.hostname or "unknown"
        port = parsed.port
        database = parsed.path.lstrip("/") or "unknown"
        if port is None:
            return f"{host}/{database}"
        return f"{host}:{port}/{database}"

    @property
    def pinpoint_token(self) -> str:
        return hashlib.sha256(self.pinpoint_secret.encode()).hexdigest()[:8]

    def derive_team_id(self, ctfd_team_id: int, ctfd_challenge_id: int) -> str:
        return derive_internal_team_id(
            team_id_salt=self.team_id_salt,
            ctfd_challenge_id=ctfd_challenge_id,
            ctfd_team_id=ctfd_team_id,
        )


settings = Settings()
