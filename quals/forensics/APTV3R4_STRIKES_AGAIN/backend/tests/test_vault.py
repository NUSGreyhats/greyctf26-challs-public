import importlib
import os

import pytest
from fastapi.testclient import TestClient

TEST_TOKEN = "A" * 67

os.environ["VAULT_TOKEN"] = TEST_TOKEN

main = importlib.import_module("app.main")
client = TestClient(main.app)


@pytest.fixture(autouse=True)
def isolated_vault(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "VAULT_DIR", tmp_path)
    main._seed_dummy_file()


def test_upload_rejects_bad_token():
    response = client.post(
        "/api/vault?upload=note.txt&token=wrong",
        files={"file": ("note.txt", b"secret notes")},
    )

    assert response.status_code == 400


def test_download_rejects_bad_token_before_filename_check():
    response = client.get("/api/vault?download=missing.txt&token=wrong")

    assert response.status_code == 400


def test_download_returns_404_for_wrong_filename_with_valid_token():
    response = client.get(f"/api/vault?download=missing.txt&token={TEST_TOKEN}")

    assert response.status_code == 404


def test_upload_is_under_maintenance_with_valid_token():
    upload_response = client.post(
        f"/api/vault?upload=../clip.txt&token={TEST_TOKEN}",
        files={"file": ("source-name.txt", b"ctf payload")},
    )

    assert upload_response.status_code == 200
    assert upload_response.text == "upload successful"


def test_upload_is_ok_without_filename_with_valid_token():
    upload_response = client.post(f"/api/vault?token={TEST_TOKEN}")

    assert upload_response.status_code == 200
    assert upload_response.text == "upload successful"


def test_upload_query_is_ok_on_get_with_valid_token():
    upload_response = client.get(f"/api/vault?upload=../../clip.txt&token={TEST_TOKEN}")

    assert upload_response.status_code == 200
    assert upload_response.text == "upload successful"


def test_seeded_dummy_file_downloads_with_valid_token():
    download_response = client.get(f"/api/vault?download=test.txt&token={TEST_TOKEN}")

    assert download_response.status_code == 200
    assert download_response.content == b"test\n"


def test_memdump_download_redirects_to_r2_without_streaming():
    download_response = client.get(
        f"/api/vault?download=mem_dump.dmp&token={TEST_TOKEN}",
        follow_redirects=False,
    )

    assert download_response.status_code == 301
    assert download_response.headers["location"] == main.R2_TRUSTED_LINK
    assert download_response.content == b""
