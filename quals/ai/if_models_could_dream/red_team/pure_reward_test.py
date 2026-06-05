#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "chall"))

from dream_rollout import load_model, observe_prefix, rollout_steps  # noqa: E402
from clean_env import find_key_locked_door_prefix  # noqa: E402


def main() -> int:
    model = load_model()
    belief, _, _, _ = observe_prefix(2026, find_key_locked_door_prefix(2026))
    best = None
    for action in range(7):
        steps = rollout_steps(model, belief, [action] * 10, sample_index=action)
        total = sum(step.reward for step in steps)
        best = max(best or (total, action, steps), (total, action, steps), key=lambda item: item[0])
    total, action, steps = best
    if max(step.cont for step in steps) > 0.95 and 1.5 < steps[0].reward < 3.2:
        raise SystemExit("pure reward selected the coherent medium-reward branch")
    print(f"pure reward: pass action={action} total={total:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
