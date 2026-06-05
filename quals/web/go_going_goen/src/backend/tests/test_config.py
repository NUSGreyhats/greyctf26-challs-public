from app.core.config import DEFAULT_METRICS_TOKEN, Settings, derive_internal_team_id


def test_database_endpoint_hides_credentials() -> None:
    settings = Settings(
        database_url="postgresql://user:secret@127.0.0.1:6432/go_going_goen",
    )

    assert settings.database_endpoint == "127.0.0.1:6432/go_going_goen"


def test_flag_reads_from_env(monkeypatch) -> None:
    monkeypatch.setenv("FLAG", "grey{from-flag}")

    settings = Settings()

    assert settings.flag == "grey{from-flag}"


def test_flag_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.delenv("FLAG", raising=False)

    settings = Settings()

    assert settings.flag == "grey{placeholder_flag}"


def test_derive_internal_team_id_is_stable() -> None:
    first = derive_internal_team_id(
        team_id_salt="salt",
        ctfd_challenge_id=7,
        ctfd_team_id=42,
    )
    second = derive_internal_team_id(
        team_id_salt="salt",
        ctfd_challenge_id=7,
        ctfd_team_id=42,
    )

    assert first == second
    assert first != derive_internal_team_id(
        team_id_salt="salt",
        ctfd_challenge_id=7,
        ctfd_team_id=43,
    )


def test_metrics_token_defaults_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("METRICS_TOKEN", raising=False)

    settings = Settings()

    assert settings.metrics_token == DEFAULT_METRICS_TOKEN


def test_pinpoint_diagnostics_timing_config_reads_from_env(monkeypatch) -> None:
    monkeypatch.setenv("PINPOINT_DIAGNOSTICS_TARGET_MS", "20")
    monkeypatch.setenv("PINPOINT_DIAGNOSTICS_ATTEST_ROUNDS", "12345")

    settings = Settings()

    assert settings.pinpoint_diagnostics_target_ms == 20
    assert settings.pinpoint_diagnostics_attest_rounds == 12345
