#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "chall"))
sys.path.insert(0, str(ROOT / "solve"))

from dream_rollout import load_model, observe_prefix, rollout_steps  # noqa: E402
from solve import decode_candidate  # noqa: E402


def digest() -> str:
    return re.search(r'EXPECTED_SHA256 = "([0-9a-f]{64})"', (ROOT / "dist" / "verify.py").read_text()).group(1)


def main() -> int:
    model = load_model()
    expected = digest()
    rng = random.Random(1337)
    for trial in range(80):
        prefix = [rng.randrange(7) for _ in range(rng.randrange(0, 8))]
        suffix = [rng.randrange(7) for _ in range(rng.randrange(4, 24))]
        belief, _, _, _ = observe_prefix(2026 + trial, prefix)
        steps = rollout_steps(model, belief, suffix, sample_index=trial)
        candidate = decode_candidate(steps)
        if hashlib.sha256(candidate.encode()).hexdigest() == expected:
            raise SystemExit("random rollout recovered the payload")
    print("random rollout: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
