from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pytest
import torch


ROOT = Path(__file__).resolve().parents[1]
CHALL = ROOT / "chall"
DIST = ROOT / "dist"
SOLVE = ROOT / "solve"
DOCKER_IMAGE = "enshittification-detector-chall-smoke"
DOCKER_CONTAINER = "enshit-smoke"
DOCKER_PORT = "35067"


def run_python(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generated():
    run_python(str(CHALL / "generate.py"))
    checks = load_module("enshit_checks", CHALL / "checks.py")
    return checks


def test_dist_contract_and_size_budget(generated) -> None:
    generated._assert_dist_shape(ROOT)

    packed = np.load(DIST / "candidates.npz")
    assert packed["x"].shape == (96, 64)
    assert packed["y"].shape == (96,)
    assert len(packed["ids"]) == 96
    assert len(list((DIST / "shadows").glob("*.pt"))) == 128


def test_public_bundle_has_no_private_leaks(generated) -> None:
    generated._assert_no_leaks(ROOT)

def test_generation_is_deterministic(generated) -> None:
    def semantic_digest() -> str:
        digest = hashlib.sha256()
        digest.update((DIST / "shadow_train_ids.json").read_bytes())
        packed = np.load(DIST / "candidates.npz")
        for key in ("x", "y", "ids"):
            digest.update(np.ascontiguousarray(packed[key]).tobytes())
        for path in sorted((DIST / "shadows").glob("*.pt")):
            try:
                state = torch.load(path, map_location="cpu", weights_only=True)
            except Exception:
                state = torch.load(path, map_location="cpu")
            for key in sorted(state):
                digest.update(key.encode())
                digest.update(state[key].detach().cpu().numpy().tobytes())
        return digest.hexdigest()

    before = semantic_digest()
    run_python(str(CHALL / "generate.py"), "--skip-checks")
    after = semantic_digest()
    assert after == before


def test_reference_solve_passes_and_baselines_fail(generated) -> None:
    generated._assert_official_solve_and_baselines(ROOT)


def test_red_team_sweep_passes_and_shortcuts_fail(generated) -> None:
    generated._assert_red_team_sweep(ROOT)


def test_server_contract_accepts_only_valid_predictions(generated, tmp_path: Path, monkeypatch) -> None:
    expected_flag = (CHALL / "real_flag.txt").read_text(encoding="utf-8").strip()
    app_module = load_module("enshit_app", CHALL / "app.py")
    common = load_module("enshit_common", CHALL / "common.py")
    issued_path = CHALL / "issued_packs.json"
    issued_path.write_text("{}\n", encoding="utf-8")
    app_module.PACK_CACHE.clear()

    client = app_module.app.test_client()
    response = client.get("/audit-pack?team=pytest-team")
    assert response.status_code == 200
    pack_path = tmp_path / "audit_pack.zip"
    pack_path.write_bytes(response.data)
    assert "pytest-team" in app_module.PACK_CACHE

    monkeypatch.setattr(app_module, "_target_state", lambda *args: pytest.fail("pack should be cached"))
    cached = client.get("/audit-pack?team=pytest-team")
    assert cached.status_code == 200
    assert cached.data == response.data

    with zipfile.ZipFile(pack_path) as zf:
        manifest = json.loads(zf.read("manifest.json").decode())
        audit_ids = json.loads(zf.read("audit_candidate_ids.json").decode())
        assert sorted(manifest["accepted_labels"]) == ["IN", "OUT"]
        assert manifest["label_meaning"]["IN"].startswith("real candidate")
        assert manifest["label_meaning"]["OUT"].startswith("fake decoy")
        assert manifest["fake_balance"] == "exactly half of this audit pack is fake"
        assert len(audit_ids) == 64
        assert "target.pt" in zf.namelist()

    issued = json.loads(issued_path.read_text(encoding="utf-8"))
    train_set = set(issued["pytest-team"]["train_ids"])
    predictions = {candidate_id: ("IN" if candidate_id in train_set else "OUT") for candidate_id in audit_ids}
    good = client.post(
        "/submit",
        json={"team": "pytest-team", "nonce": manifest["nonce"], "predictions": predictions},
    )
    assert good.data.decode().strip() == expected_flag

    bad_nonce = client.post(
        "/submit",
        json={"team": "pytest-team", "nonce": "bad", "predictions": predictions},
    )
    assert bad_nonce.data.decode().strip() == "submission rejected"

    assert len(common.ACCEPTED_LABELS) == 2


@pytest.mark.skipif(
    not os.environ.get("RUN_DOCKER_SMOKE") or shutil.which("docker") is None,
    reason="set RUN_DOCKER_SMOKE=1 with docker available",
)
def test_docker_flask_end_to_end(generated, tmp_path: Path) -> None:
    expected_flag = (CHALL / "real_flag.txt").read_text(encoding="utf-8").strip()
    audit_pack = tmp_path / "audit_pack.zip"
    payload = tmp_path / "payload.json"

    build = subprocess.run(
        ["docker", "build", "-f", "chall/Dockerfile", "-t", DOCKER_IMAGE, "."],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr

    subprocess.run(["docker", "rm", "-f", DOCKER_CONTAINER], capture_output=True, text=True, check=False)
    run = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            DOCKER_CONTAINER,
            "-p",
            f"127.0.0.1:{DOCKER_PORT}:5000",
            DOCKER_IMAGE,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr

    try:
        url = f"http://127.0.0.1:{DOCKER_PORT}"
        last_error = ""
        for _ in range(60):
            fetch = subprocess.run(
                ["curl", "-fsS", f"{url}/audit-pack?team=docker-smoke", "-o", str(audit_pack)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            if fetch.returncode == 0:
                break
            last_error = fetch.stdout + fetch.stderr
            time.sleep(1)
        else:
            logs = subprocess.run(["docker", "logs", DOCKER_CONTAINER], capture_output=True, text=True, check=False)
            raise AssertionError(last_error + "\n" + logs.stdout + logs.stderr)

        with zipfile.ZipFile(audit_pack) as zf:
            assert sorted(zf.namelist()) == ["audit_candidate_ids.json", "manifest.json", "target.pt"]

        solved = subprocess.run(
            [
                sys.executable,
                str(SOLVE / "solve.py"),
                "--dist",
                str(DIST),
                "--audit-pack",
                str(audit_pack),
                "--out",
                str(payload),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert solved.returncode == 0, solved.stdout + solved.stderr

        submitted = subprocess.run(
            [
                sys.executable,
                str(SOLVE / "submit.py"),
                "--url",
                url,
                "--payload",
                str(payload),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert submitted.returncode == 0, submitted.stdout + submitted.stderr
        assert submitted.stdout.strip() == expected_flag
    finally:
        subprocess.run(["docker", "rm", "-f", DOCKER_CONTAINER], capture_output=True, text=True, check=False)
