#!/usr/bin/env python3
from __future__ import annotations

import pickle
import sys
import zlib
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path = [
    entry
    for entry in sys.path
    if Path(entry or ".").resolve() != SCRIPT_DIR
]

import numpy as np


MAGIC = b"SVSLACK\x00"
ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"


class DualLinearInference:
    def __init__(self, artifact: Any):
        # The artifact is intentionally stripped down, but these dual-form
        # fields are enough to reconstruct the public linear decision function.
        required = ("support_vectors_", "dual_coef_", "intercept_", "C")
        missing = [attr for attr in required if not hasattr(artifact, attr)]
        if missing:
            raise TypeError(f"missing dual artifact fields: {', '.join(missing)}")
        self.support_vectors_ = np.asarray(artifact.support_vectors_, dtype=float)
        self.dual_coef_ = np.asarray(artifact.dual_coef_, dtype=float)
        self.intercept_ = np.asarray(artifact.intercept_, dtype=float)
        self.C = float(artifact.C)

    def primal_weight(self) -> np.ndarray:
        # For a linear SVM, dual_coef_[0] stores alpha_i * y_i, so multiplying
        # by support_vectors_ reconstructs the hidden primal normal vector.
        return self.dual_coef_[0] @ self.support_vectors_

    def decision_function(self, x: np.ndarray) -> np.ndarray:
        values = np.asarray(x, dtype=float)
        return values @ self.primal_weight() + self.intercept_[0]

    def predict(self, x: np.ndarray) -> np.ndarray:
        return np.where(self.decision_function(x) >= 0.0, 1, -1)


def bits_to_bytes(bits: np.ndarray) -> bytes:
    out = bytearray()
    for i in range(0, len(bits) - 7, 8):
        v = 0
        for bit in bits[i : i + 8]:
            v = (v << 1) | int(bit)
        out.append(v)
    return bytes(out)


def parse_payload(bits: np.ndarray) -> str | None:
    # The bitstream carries self-checking framing. This avoids accepting random
    # thresholding artifacts that happen to decode as UTF-8.
    data = bits_to_bytes(bits)
    if not data.startswith(MAGIC):
        return None
    pos = len(MAGIC)
    if len(data) < pos + 2:
        return None
    length = int.from_bytes(data[pos : pos + 2], "big")
    pos += 2
    end = pos + length
    if len(data) < end + 4:
        return None
    flag = data[pos:end]
    crc = int.from_bytes(data[end : end + 4], "big")
    if (zlib.crc32(flag) & 0xFFFFFFFF) != crc:
        return None
    try:
        return flag.decode("utf-8")
    except UnicodeDecodeError:
        return None


def bounded_candidate_slacks(model: DualLinearInference) -> np.ndarray:
    support_vectors = model.support_vectors_
    signed = model.dual_coef_[0]
    alpha = np.abs(signed)
    # The sign of alpha_i*y_i recovers the support-vector label y_i.
    labels = np.sign(signed)
    # Reconstruct the linear classifier and evaluate every support-vector
    # margin using only public dual-form fields.
    w = signed @ support_vectors
    b = model.intercept_[0]

    margins = labels * (support_vectors @ w + b)
    slack = np.maximum(0.0, 1.0 - margins)
    # Upper-bound dual variables are the bounded support vectors where the
    # challenge hides the bit bands.
    bounded = np.isclose(alpha, model.C, rtol=1e-5, atol=1e-6)
    candidates = bounded
    if int(np.sum(candidates)) < 8:
        raise RuntimeError("not enough bounded support vectors")

    # The artifact preserves support-vector/dual-coefficient row order. After
    # masking to bounded vectors, that public row order is the bitstream order.
    return slack[candidates]


def slack_bits(slacks: np.ndarray) -> np.ndarray:
    # The slack values form two one-dimensional bands. The largest gap in the
    # sorted values separates those bands without hardcoding generator numbers.
    ordered = np.sort(slacks)
    gaps = np.diff(ordered)
    if gaps.size == 0:
        raise RuntimeError("not enough slack values to split into bands")
    split = int(np.argmax(gaps))
    threshold = float((ordered[split] + ordered[split + 1]) / 2.0)
    return (slacks > threshold).astype(np.uint8)


def recover_flag(artifact: Any) -> str:
    model = DualLinearInference(artifact)
    ordered_slacks = bounded_candidate_slacks(model)
    bits = slack_bits(ordered_slacks)
    flag = parse_payload(bits)
    if flag is not None:
        return flag
    raise RuntimeError("failed to recover benchmark identifier")


def main() -> int:
    with (DIST_DIR / "svc_dual_params.pkl").open("rb") as f:
        artifact = pickle.load(f)
    print(recover_flag(artifact))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
