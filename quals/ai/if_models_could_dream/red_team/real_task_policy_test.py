#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT / "chall"))

from policy import evaluate_exported_policy, run_exported_policy_episode  # noqa: E402


def main() -> int:
    policy = DIST / "model" / "policy.pt"
    if not policy.exists():
        raise SystemExit("missing dist/model/policy.pt; run chall/make_challenge.py first")
    ok, reward, steps = run_exported_policy_episode(policy, 2026, max_steps=256)
    if not ok:
        raise SystemExit(f"policy failed seed 2026: reward={reward:.6f} steps={steps}")
    heldout = evaluate_exported_policy(policy, range(2200, 2250), max_steps=256)
    if heldout["success_rate"] < 0.90:
        raise SystemExit(f"held-out success below target: {heldout}")
    print(
        "real task policy: pass "
        f"seed2026_reward={reward:.6f} heldout_success={heldout['success_rate']:.3f} "
        f"heldout_mean_reward={heldout['mean_reward']:.6f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
