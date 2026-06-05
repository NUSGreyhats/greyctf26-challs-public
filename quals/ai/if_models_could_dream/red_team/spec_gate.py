#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
EXPECTED_DIST = {
    "logs/train_summary.txt",
    "model/config.json",
    "model/policy.pt",
    "model/encoder.pt",
    "model/rssm.pt",
    "model/decoder.pt",
    "model/reward_head.pt",
    "model/continue_head.pt",
    "model/value_head.pt",
    "requirements.txt",
    "start_seed.txt",
    "verify.py",
}


def run(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def sha_from_verifier(path: Path) -> str:
    match = re.search(r'EXPECTED_SHA256 = "([0-9a-f]{64})"', path.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit("verifier digest missing")
    return match.group(1)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def assert_dist_files() -> None:
    found = {str(path.relative_to(DIST)) for path in DIST.rglob("*") if path.is_file()}
    missing = EXPECTED_DIST - found
    extra = found - EXPECTED_DIST
    if missing or extra:
        raise SystemExit(f"dist file mismatch: missing={sorted(missing)} extra={sorted(extra)}")


def assert_no_public_plaintext() -> None:
    markers = [b"grey{", b"d3LulU", b"Som3T1me5", b"gooD_s0LUlu"]
    for path in DIST.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            for marker in markers:
                if marker in data:
                    raise SystemExit(f"public plaintext marker found in {path}")


def assert_tool_modes() -> None:
    work = ROOT / ".spec_gate_tmp"
    work.mkdir(exist_ok=True)
    prefix = work / "prefix.txt"
    suffix = work / "suffix.txt"
    prefix_actions = run("chall/clean_env.py", "--seed", "2026", "--print-prefix").stdout.strip()
    prefix.write_text(prefix_actions + "\n", encoding="utf-8")
    suffix.write_text("5 2 5 2 5 2 5 2 5\n", encoding="utf-8")
    run("chall/dream_rollout.py", "rollout", "--seed", "2026", "--prefix", str(prefix), "--suffix", str(suffix), "--sample-index", "1", "--out", str(work / "rollout"))
    run("chall/dream_rollout.py", "sample", "--seed", "2026", "--prefix", str(prefix), "--suffix", str(suffix), "--samples", "8", "--out", str(work / "samples"))
    run("chall/dream_rollout.py", "probe", "--seed", "2026", "--prefix", str(prefix), "--out", str(work / "probe"))
    for required in [
        work / "rollout" / "contact_sheet.png",
        work / "rollout" / "rewards.csv",
        work / "samples" / "summary.csv",
        work / "samples" / "all_samples.png",
        work / "probe" / "summary.csv",
    ]:
        if not required.exists():
            raise SystemExit(f"tool output missing: {required}")


def assert_reward_and_anomaly_decoys() -> None:
    work = ROOT / ".spec_gate_tmp"
    probe = read_csv(work / "probe" / "summary.csv")
    by_reward = max(probe, key=lambda row: float(row["predicted_reward"]))
    by_mse = max(probe, key=lambda row: float(row["image_mse"]))
    if float(by_reward["predicted_continue"]) > 0.95 and 0.8 <= float(by_reward["predicted_reward"]) <= 3.2:
        raise SystemExit("highest one-step reward looks like the coherent branch")
    if float(by_mse["predicted_continue"]) > 0.95 and 0.8 <= float(by_mse["predicted_reward"]) <= 3.2:
        raise SystemExit("highest one-step anomaly looks like the coherent branch")


def assert_reference_and_visual_solve() -> None:
    digest = sha_from_verifier(DIST / "verify.py")
    solved = run("solve/solve.py").stdout.strip().splitlines()[-1]
    if hashlib.sha256(solved.encode()).hexdigest() != digest:
        raise SystemExit("reference solve hash mismatch")
    visual = run("solve/visual_solve.py", "--out", "solve/visual_out", "--samples", "64").stdout.strip().splitlines()[-1]
    if visual != solved:
        raise SystemExit("visual solve and reference solve diverged")
    for path in [
        ROOT / "solve" / "visual_out" / "06_episode_to_lamps.mp4",
        ROOT / "solve" / "visual_out" / "06_episode_to_lamps.gif",
    ]:
        if not path.exists() or path.stat().st_size < 1000:
            raise SystemExit(f"visual solve video missing or too small: {path}")


def main() -> int:
    found = {str(path.relative_to(DIST)) for path in DIST.rglob("*") if path.is_file()} if DIST.exists() else set()
    if not EXPECTED_DIST.issubset(found):
        run("chall/make_challenge.py")
    assert_dist_files()
    assert_no_public_plaintext()
    assert_tool_modes()
    assert_reward_and_anomaly_decoys()
    assert_reference_and_visual_solve()
    checked = run("dist/verify.py", input_text=(ROOT / "solve" / "visual_out" / "recovered.txt").read_text(encoding="utf-8"))
    if checked.stdout.strip() != "correct":
        raise SystemExit("dist verifier rejected visual solve output")
    print("spec gate: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
