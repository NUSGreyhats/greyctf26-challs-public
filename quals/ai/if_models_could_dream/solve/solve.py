#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

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


def suffix(step_count: int) -> list[int]:
    actions: list[int] = []
    while len(actions) < step_count:
        actions.extend([5, 2])
    return actions[:step_count]


def byte_from_frame(frame) -> int:
    candidates = detect_lamp_candidates(frame)
    if not candidates:
        return -1
    for _, bits in candidates[:8]:
        value = 0
        for bit in bits:
            value = (value << 1) | int(bit)
        if value in (10, 13) or 32 <= value <= 126:
            return value
    bits = candidates[0][1]
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value


def detect_lamp_bits(frame) -> list[int] | None:
    candidates = detect_lamp_candidates(frame)
    return None if not candidates else candidates[0][1]


def detect_lamp_candidates(frame) -> list[tuple[float, list[int]]]:
    red = np.asarray(frame, dtype=np.float32)[:, :, 0]
    lamp_w = 4
    lamp_h = 5
    spacing = 5
    row_w = spacing * 7 + lamp_w
    padded = np.pad(red, ((1, 0), (1, 0)), mode="constant")
    integral = padded.cumsum(axis=0).cumsum(axis=1)
    sums = (
        integral[lamp_h:, lamp_w:]
        - integral[:-lamp_h, lamp_w:]
        - integral[lamp_h:, :-lamp_w]
        + integral[:-lamp_h, :-lamp_w]
    )
    means = sums / float(lamp_w * lamp_h)
    max_x0 = red.shape[1] - row_w + 1
    if max_x0 <= 0:
        return None
    cells = np.stack([means[:, i * spacing : i * spacing + max_x0] for i in range(8)], axis=0)
    high = cells.max(axis=0)
    low = cells.min(axis=0)
    contrast = high - low
    cutoff = (high + low) / 2.0
    binary_score = np.abs(cells - cutoff[None, :, :]).mean(axis=0)
    score = np.where(contrast >= 95, contrast + binary_score, -1.0)
    for y in range(score.shape[0]):
        for x0 in range(score.shape[1]):
            if score[y, x0] < 0:
                continue
            x1 = x0 - 2
            x2 = x0 + row_w + 1
            yt = y - 5
            yb = y + lamp_h + 4
            if x1 < 0 or yt < 0 or x2 >= red.shape[1] or yb >= red.shape[0]:
                score[y, x0] = -1
                continue
            top = float(red[yt, x1 : x2 + 1].mean())
            bottom = float(red[yb, x1 : x2 + 1].mean())
            left = float(red[yt : yb + 1, x1].mean())
            right = float(red[yt : yb + 1, x2].mean())
            backing = float(red[y - 1, x0 - 1 : x0 + row_w + 1].mean())
            score[y, x0] += 0.6 * ((top + bottom + left + right) / 4.0) - 0.15 * backing
    flat_scores = score.reshape(-1)
    valid = np.flatnonzero(flat_scores >= 0)
    if valid.size == 0:
        return []
    order = valid[np.argsort(flat_scores[valid])[-12:]][::-1]
    out: list[tuple[float, list[int]]] = []
    seen: set[tuple[int, ...]] = set()
    for flat in order:
        y, x0 = np.unravel_index(int(flat), score.shape)
        bits = tuple(int(cell > cutoff[y, x0]) for cell in cells[:, y, x0])
        if bits in seen:
            continue
        seen.add(bits)
        out.append((float(score[y, x0]), list(bits)))
    return out


def decode_candidate(steps) -> str:
    values: list[int] = []
    for idx, step in enumerate(steps):
        if idx != 0 and idx % 2 == 0:
            continue
        b = byte_from_frame(step.frame)
        if b < 0:
            continue
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
    panel_count = int(model["rssm"]["rollout_steps"])
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
