#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "chall"))

from clean_env import find_expert_plan, find_key_locked_door_prefix, run_actions  # noqa: E402


def main() -> int:
    good = find_key_locked_door_prefix(2026)
    probes = [
        [],
        good,
        good + [2, 2, 2],
        [1, 1, 2, 2, 3, 5, 2, 6],
    ]
    for seed in range(2026, 2036):
        expert = find_expert_plan(seed)
        _, expert_info, expert_trace = run_actions(seed, expert)
        if expert_trace[-1]["reward"] <= 0.0:
            raise SystemExit(f"expert did not solve training seed {seed}")
        if expert_info.get("binary_lamp_corridor"):
            raise SystemExit("clean simulator exposed dream-only marker")
        for actions in probes:
            _, info, trace = run_actions(seed, actions)
            if any(item["reward"] > 0.99 for item in trace):
                raise SystemExit("unexpected clean reward above documented max")
            if info.get("binary_lamp_corridor"):
                raise SystemExit("clean simulator exposed dream-only marker")
    solved = 0
    for seed in range(2200, 2250):
        expert = find_expert_plan(seed)
        _, _, trace = run_actions(seed, expert)
        solved += int(trace[-1]["reward"] > 0.0)
    if solved != 50:
        raise SystemExit(f"expert held-out failures: {50 - solved}")
    print("clean simulator: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
