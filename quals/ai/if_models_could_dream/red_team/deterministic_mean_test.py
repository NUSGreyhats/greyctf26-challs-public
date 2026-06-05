#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "chall"))
sys.path.insert(0, str(ROOT / "solve"))

from dream_rollout import load_model, observe_prefix, rollout_steps  # noqa: E402
from solve import decode_candidate, good_prefix, suffix  # noqa: E402


def main() -> int:
    model = load_model()
    digest = re.search(r'EXPECTED_SHA256 = "([0-9a-f]{64})"', (ROOT / "dist" / "verify.py").read_text()).group(1)
    belief, _, _, _ = observe_prefix(2026, good_prefix(2026))
    steps = rollout_steps(model, belief, suffix(int(model["rssm"]["horizon"])), deterministic=True)
    candidate = decode_candidate(steps)
    if hashlib.sha256(candidate.encode()).hexdigest() == digest:
        raise SystemExit("deterministic mean exposed the payload")
    print("deterministic mean: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
