#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "chall"))
sys.path.insert(0, str(ROOT / "solve"))

from dream_rollout import Belief, load_model, rollout_steps  # noqa: E402
from solve import decode_candidate, suffix  # noqa: E402


def main() -> int:
    model = load_model()
    digest = re.search(r'EXPECTED_SHA256 = "([0-9a-f]{64})"', (ROOT / "dist" / "verify.py").read_text()).group(1)
    image_only = Belief(
        seed=2026,
        correct_history=False,
        saw_key=False,
        saw_door=True,
        dropped=False,
        failed_training=False,
        features=(0.0, 0.0, 0.0, 0.0),
        anchor_frame=np.zeros((56, 56, 3), dtype=np.uint8),
    )
    for sample in range(96):
        steps = rollout_steps(model, image_only, suffix(int(model["rssm"]["horizon"])), sample_index=sample)
        candidate = decode_candidate(steps)
        if hashlib.sha256(candidate.encode()).hexdigest() == digest:
            raise SystemExit("image-only anchor recovered the payload")
    print("image-only anchor: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
