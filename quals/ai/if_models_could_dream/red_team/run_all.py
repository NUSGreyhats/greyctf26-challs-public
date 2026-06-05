#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = [
    "static_leakage_test.py",
    "dist_hint_scan_test.py",
    "clean_simulator_test.py",
    "real_task_policy_test.py",
    "regular_path_no_flag_test.py",
    "random_rollout_test.py",
    "pure_reward_test.py",
    "one_step_anomaly_test.py",
    "direct_tensor_shortcut_test.py",
    "image_only_anchor_test.py",
    "deterministic_mean_test.py",
    "reference_solve_test.py",
    "dist_bundle_test.py",
    "spec_gate.py",
]


def main() -> int:
    for test in TESTS:
        subprocess.run([sys.executable, str(ROOT / "red_team" / test)], cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
