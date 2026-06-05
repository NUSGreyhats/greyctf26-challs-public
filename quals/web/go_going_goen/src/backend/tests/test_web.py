from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.web import configure_spa


def build_client(static_dir: Path) -> TestClient:
    app = FastAPI()
    configure_spa(app, static_dir)
    return TestClient(app)


def test_configure_spa_serves_index_at_root_and_nested_paths(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>hello</html>")

    client = build_client(static_dir)

    root_response = client.get("/")
    nested_response = client.get("/progress")

    assert root_response.status_code == 200
    assert root_response.text == "<html>hello</html>"
    assert nested_response.status_code == 200
    assert nested_response.text == "<html>hello</html>"


def test_configure_spa_serves_built_assets(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html>hello</html>")
    (assets_dir / "app.js").write_text("console.log('ok');")

    client = build_client(static_dir)
    response = client.get("/assets/app.js")

    assert response.status_code == 200
    assert "console.log('ok');" in response.text


def test_configure_spa_does_not_mask_api_paths(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>hello</html>")

    client = build_client(static_dir)
    response = client.get("/api/unknown")
    metrics_response = client.get("/metrics")

    assert response.status_code == 404
    assert metrics_response.status_code == 404
