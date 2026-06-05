#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "chall"))

from dream_rollout import image_mse, load_model, observe_prefix, rollout_steps  # noqa: E402
from clean_env import find_key_locked_door_prefix, run_actions  # noqa: E402


def main() -> int:
    model = load_model()
    prefix = find_key_locked_door_prefix(2026)
    belief, _, _, _ = observe_prefix(2026, prefix)
    ranked = []
    for action in range(7):
        real_next, _, _ = run_actions(2026, prefix + [action])
        pred = rollout_steps(model, belief, [action], sample_index=action)[0]
        ranked.append((image_mse(real_next, pred.frame), pred.reward, pred.cont, action))
    ranked.sort(reverse=True)
    top_mse, top_reward, top_cont, top_action = ranked[0]
    if top_cont > 0.95 and top_reward < 3.2:
        raise SystemExit("one-step anomaly ranked the coherent branch first")
    print(f"one-step anomaly: pass action={top_action} mse={top_mse:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
