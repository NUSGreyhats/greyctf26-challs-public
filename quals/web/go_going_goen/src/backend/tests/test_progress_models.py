from app.models.progress import EMPTY_PROGRESS, ProgressState


def test_progress_payload_unlocks_source_when_stage_is_accessible() -> None:
    payload = ProgressState(
        stage1_cleared=True,
        stage2_cleared=False,
        stage3_cleared=False,
    ).as_payload()

    assert payload["downloads"] == {
        "stage1": True,
        "stage2": True,
        "stage3": False,
    }


def test_empty_progress_defaults_stage1_download_to_available() -> None:
    payload = EMPTY_PROGRESS.as_payload()

    assert payload["downloads"] == {
        "stage1": True,
        "stage2": False,
        "stage3": False,
    }
