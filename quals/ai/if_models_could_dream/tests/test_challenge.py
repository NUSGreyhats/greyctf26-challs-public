from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
EXPECTED_DIST = {
    "verify.py",
    "requirements.txt",
    "start_seed.txt",
    "model/config.json",
    "model/policy.pt",
    "model/encoder.pt",
    "model/rssm.pt",
    "model/decoder.pt",
    "model/reward_head.pt",
    "model/continue_head.pt",
    "model/value_head.pt",
    "logs/train_summary.txt",
}


def run_python(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def verifier_digest() -> str:
    match = re.search(r'EXPECTED_SHA256 = "([0-9a-f]{64})"', (DIST / "verify.py").read_text(encoding="utf-8"))
    assert match
    return match.group(1)


@pytest.fixture(scope="session")
def generated_challenge() -> None:
    found = {str(path.relative_to(DIST)) for path in DIST.rglob("*") if path.is_file()} if DIST.exists() else set()
    if not EXPECTED_DIST.issubset(found):
        run_python("chall/make_challenge.py")


def test_generate_solve_and_verify(generated_challenge: None) -> None:
    result = run_python("solve/solve.py")
    recovered = result.stdout.strip().splitlines()[-1]
    assert hashlib.sha256(recovered.encode()).hexdigest() == verifier_digest()
    checked = run_python("dist/verify.py", recovered)
    assert checked.stdout.strip() == "correct"


def test_visual_solve_has_pictures_and_video(generated_challenge: None) -> None:
    run_python("solve/visual_solve.py", "--out", "solve/visual_out", "--samples", "64")
    expected_pictures = [
        "00_readme.png",
        "01_real_lockedroom_full_map.png",
        "01_clean_prefix_sheet.png",
        "02_one_step_probe_real_vs_dream.png",
        "03_sampled_futures_overview.png",
        "04_corridor_panels.png",
        "05_decoded_panel_bits.png",
    ]
    for name in expected_pictures:
        assert (ROOT / "solve" / "visual_out" / name).stat().st_size > 100
    assert not (ROOT / "solve" / "visual_out" / "06_model_view.gif").exists()
    assert not (ROOT / "solve" / "visual_out" / "06_model_view.mp4").exists()
    assert (ROOT / "solve" / "visual_out" / "06_episode_to_lamps.mp4").stat().st_size > 1000
    assert (ROOT / "solve" / "visual_out" / "06_episode_to_lamps.gif").stat().st_size > 1000


def test_red_team_suite(generated_challenge: None) -> None:
    run_python("red_team/run_all.py")


def test_dist_bundle_shape_and_leakage(generated_challenge: None) -> None:
    found = {str(path.relative_to(DIST)) for path in DIST.rglob("*") if path.is_file()}
    assert EXPECTED_DIST == found
    forbidden_names = {"ORGANIZER_NOTES.md", "AUDIT.md", "SCRATCHPAD.md", "make_challenge.py", "make_release.py", "solve.py", "visual_solve.py"}
    assert not any(path.name in forbidden_names for path in DIST.rglob("*"))
    for path in DIST.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            assert b"grey{" not in data
            assert b"d3LulU" not in data
            assert b"Som3T1me5" not in data
            assert b"gooD_s0LUlu" not in data


def test_internal_rollout_tool_runs(generated_challenge: None, tmp_path: Path) -> None:
    prefix = tmp_path / "prefix.txt"
    suffix = tmp_path / "suffix.txt"
    out = tmp_path / "sample_check"
    prefix_actions = run_python("chall/clean_env.py", "--seed", "2026", "--print-prefix").stdout.strip()
    prefix.write_text(prefix_actions + "\n", encoding="utf-8")
    suffix.write_text("5 2 5 2 5 2 5\n", encoding="utf-8")
    run_python("chall/dream_rollout.py", "sample", "--seed", "2026", "--prefix", str(prefix), "--suffix", str(suffix), "--samples", "4", "--out", str(out))
    assert (out / "summary.csv").exists()
    assert (out / "all_samples.png").exists()
