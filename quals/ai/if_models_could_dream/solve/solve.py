#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "chall"))

from clean_env import find_reward_desire_prefix  # noqa: E402
from dream_rollout import load_model, observe_prefix, rollout_steps  # noqa: E402


def good_prefix(seed: int = 2026) -> list[int]:
    return find_reward_desire_prefix(seed)


def expected_digest() -> str:
    source = (ROOT / "dist" / "verify.py").read_text(encoding="utf-8")
    match = re.search(r'EXPECTED_SHA256 = "([0-9a-f]{64})"', source)
    if not match:
        raise RuntimeError("could not locate verifier digest")
    return match.group(1)


def suffix(panel_count: int) -> list[int]:
    actions = [5]
    for _ in range(panel_count - 1):
        actions.extend([2, 5])
    return actions


def byte_from_frame(frame) -> int:
    value = 0
    for i in range(8):
        x = 9 + i * 5
        lit = int(frame[20, x, 0]) > 140
        value = (value << 1) | int(lit)
    return value


def decode_candidate(steps) -> str:
    values: list[int] = []
    for idx, step in enumerate(steps):
        if idx != 0 and idx % 2 == 0:
            continue
        reds = [int(step.frame[20, 9 + i * 5, 0]) for i in range(8)]
        if max(reds) - min(reds) < 120:
            continue
        b = byte_from_frame(step.frame)
        printableish = b in (10, 13) or 32 <= b <= 126
        if printableish:
            values.append(b)
    try:
        return bytes(values).decode("ascii")
    except UnicodeDecodeError:
        return ""


def verifier_accepts(candidate: str, digest: str) -> bool:
    return hmac.compare_digest(hashlib.sha256(candidate.encode()).hexdigest(), digest)


def main() -> int:
    model = load_model()
    digest = expected_digest()
    panel_count = int(model["rssm"]["horizon"])
    prefix = good_prefix(int(model["config"]["seed"]))
    belief, _, _, _ = observe_prefix(int(model["config"]["seed"]), prefix)
    if not belief.correct_history:
        raise RuntimeError("reference prefix did not build the expected exploration-conditioned recurrent state")

    dream_suffix = suffix(panel_count)
    for sample in range(256):
        steps = rollout_steps(model, belief, dream_suffix, sample_index=sample, deterministic=False)
        candidate = decode_candidate(steps)
        if verifier_accepts(candidate, digest):
            checked = subprocess.run([sys.executable, str(ROOT / "dist" / "verify.py"), candidate], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            if checked.stdout.strip() != "correct":
                raise RuntimeError("local hash and verifier disagreed")
            print(candidate)
            return 0
    raise RuntimeError("no coherent candidate found")


if __name__ == "__main__":
    raise SystemExit(main())
