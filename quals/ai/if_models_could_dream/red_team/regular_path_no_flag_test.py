#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "chall"))
sys.path.insert(0, str(ROOT / "solve"))

from clean_env import actions_to_face, adjacent_positions, bfs_actions, expert_action_from_env, extracted_info, find_key_locked_door_prefix, make_env, target_locked_door_and_key  # noqa: E402
from dream_rollout import load_model, observe_prefix, rollout_steps  # noqa: E402
from solve import decode_candidate, suffix  # noqa: E402


def no_other_doors_prefix(seed: int = 2026) -> list[int]:
    env = make_env(seed)
    _, _ = env.reset(seed=seed)
    door, _ = target_locked_door_and_key(env)
    if door is None:
        raise RuntimeError("locked door missing")
    door_pos = (door[0], door[1])
    info = extracted_info(env)
    actions = bfs_actions(env, (*info["agent_pos"], info["agent_dir"]), adjacent_positions(door_pos))
    for action in actions:
        env.step(action)
    face = actions_to_face(env, door_pos)
    actions.extend(face)
    for action in face:
        env.step(action)
    for action in [5, 6, 5]:
        actions.append(action)
        env.step(action)
    for _ in range(256 - len(actions)):
        action = expert_action_from_env(env)
        actions.append(action)
        _, reward, terminated, truncated, _ = env.step(action)
        if terminated or truncated or reward > 0.0:
            break
        if not target_locked_door_and_key(env)[0]:
            break
    return actions


def assert_no_payload(model: dict, digest: str, prefix: list[int], label: str) -> None:
    belief, _, _, _ = observe_prefix(2026, prefix)
    if belief.correct_history:
        raise SystemExit(f"{label} entered the exploration-conditioned branch")
    dream_suffix = suffix(int(model["rssm"]["rollout_steps"]))
    for sample in range(256):
        steps = rollout_steps(model, belief, dream_suffix, sample_index=sample)
        candidate = decode_candidate(steps)
        if hashlib.sha256(candidate.encode()).hexdigest() == digest:
            raise SystemExit(f"{label} recovered the payload")


def main() -> int:
    model = load_model()
    digest = re.search(r'EXPECTED_SHA256 = "([0-9a-f]{64})"', (ROOT / "dist" / "verify.py").read_text()).group(1)
    assert_no_payload(model, digest, find_key_locked_door_prefix(2026), "ordinary successful setup")
    assert_no_payload(model, digest, no_other_doors_prefix(2026), "locked-door setup without other-door inspection")
    print("regular path no flag: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
