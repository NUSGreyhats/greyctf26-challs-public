#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import pickle
import shutil
import subprocess
import sys
import zlib
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True

import numpy as np
from sklearn.metrics import accuracy_score
from sklearn.svm import SVC


SEED = 2026
D = 12
C = 0.05

MAGIC = b"SVSLACK\x00"
NORMAL_SCALE = 0.3
ORDER_STEP = 0.012
SLACK_ZERO = 0.45
SLACK_ONE = 0.75
PAYLOAD_NOISE = 0.0001
DECOY_NOISE = 0.005
N_ANCHOR_POSITIONS = 20
N_DECOYS = 400

ROOT = Path(__file__).resolve().parents[1]
CHALL_DIR = ROOT / "chall"
DIST_DIR = ROOT / "dist"


def bytes_to_bits(data: bytes) -> np.ndarray:
    out = []
    for b in data:
        for shift in range(7, -1, -1):
            out.append((b >> shift) & 1)
    return np.array(out, dtype=np.uint8)


def read_flag() -> bytes:
    flag = (CHALL_DIR / "flag.txt").read_bytes().strip()
    if not (flag.startswith(b"grey{") and flag.endswith(b"}")):
        raise ValueError("flag must use grey{...} format")
    return flag


def build_payload(flag: bytes) -> tuple[bytes, np.ndarray]:
    if len(flag) > 0xFFFF:
        raise ValueError("flag is too long")
    crc = (zlib.crc32(flag) & 0xFFFFFFFF).to_bytes(4, "big")
    payload = MAGIC + len(flag).to_bytes(2, "big") + flag + crc
    return payload, bytes_to_bits(payload)


def build_basis(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    q, _ = np.linalg.qr(rng.normal(size=(D, D)))
    return q[:, 0], q[:, 1]


def build_training_matrix(
    rng: np.random.Generator, payload_bits: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    normal_axis, order_axis = build_basis(rng)
    x_rows = []
    y_rows = []
    payload_index = []

    midpoint = (payload_bits.size - 1) / 2
    for i, bit in enumerate(payload_bits):
        position = (i - midpoint) * ORDER_STEP
        label = 1 if i % 2 else -1
        slack = SLACK_ONE if int(bit) else SLACK_ZERO
        x = (
            position * order_axis
            + label * NORMAL_SCALE * (1.0 - slack) * normal_axis
            + PAYLOAD_NOISE * rng.normal(size=D)
        )
        x_rows.append(x)
        y_rows.append(label)
        payload_index.append(i)

    for position in np.linspace(-4.0, 4.0, N_ANCHOR_POSITIONS):
        for label in (-1, 1):
            x_rows.append(position * order_axis + label * NORMAL_SCALE * normal_axis)
            y_rows.append(label)
            payload_index.append(-1)

    for _ in range(N_DECOYS):
        label = 1 if rng.integers(0, 2) else -1
        position = rng.uniform(-7.0, 7.0)
        distance = rng.uniform(1.5, 2.5)
        x = (
            position * order_axis
            + label * NORMAL_SCALE * distance * normal_axis
            + DECOY_NOISE * rng.normal(size=D)
        )
        x_rows.append(x)
        y_rows.append(label)
        payload_index.append(-1)

    return np.array(x_rows), np.array(y_rows), np.array(payload_index)


def clean_dist() -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    for path in DIST_DIR.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def write_verifier(flag: bytes) -> None:
    digest = hashlib.sha256(flag).hexdigest()
    (DIST_DIR / "verify.py").write_text(
        f'''#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import sys


EXPECTED_SHA256 = "{digest}"


def read_candidate() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    return sys.stdin.read().strip()


def main() -> int:
    candidate = read_candidate().encode()
    actual = hashlib.sha256(candidate).hexdigest()
    print("correct" if hmac.compare_digest(actual, EXPECTED_SHA256) else "incorrect")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
        encoding="utf-8",
    )


def write_requirements() -> None:
    (DIST_DIR / "requirements.txt").write_text("numpy\nscikit-learn\n", encoding="utf-8")


def slack_values(model: SVC) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    alpha = np.abs(model.dual_coef_[0])
    signed_labels = np.sign(model.dual_coef_[0])
    margins = signed_labels * (model.support_vectors_ @ model.coef_[0] + model.intercept_[0])
    slack = np.maximum(0.0, 1.0 - margins)
    return alpha, signed_labels, slack


def dual_artifact_from_model(model: SVC, support_payload_index: np.ndarray) -> SimpleNamespace:
    payload_rows = np.flatnonzero(support_payload_index >= 0)
    payload_rows = payload_rows[np.argsort(support_payload_index[payload_rows])]
    non_payload_rows = np.flatnonzero(support_payload_index < 0)
    row_order = np.concatenate([payload_rows, non_payload_rows])
    return SimpleNamespace(
        support_vectors_=np.array(model.support_vectors_[row_order], copy=True),
        dual_coef_=np.array(model.dual_coef_[:, row_order], copy=True),
        intercept_=np.array(model.intercept_, copy=True),
        C=float(model.C),
    )


def run_solver_check(flag: bytes) -> bool:
    solver = ROOT / "solve" / "solve.py"
    if not solver.exists():
        return False
    result = subprocess.run(
        [sys.executable, str(solver)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return False
    return result.stdout.strip().splitlines()[-1] == flag.decode()


def main() -> int:
    flag = read_flag()
    payload, payload_bits = build_payload(flag)

    rng = np.random.default_rng(SEED)
    x_train, y_train, payload_index = build_training_matrix(rng, payload_bits)

    model = SVC(kernel="linear", C=C, tol=1e-7, shrinking=False)
    model.fit(x_train, y_train)

    support_payload_index = payload_index[model.support_]
    alpha, _, slack = slack_values(model)
    bounded = np.isclose(alpha, C, rtol=1e-5, atol=1e-6)
    slack_candidates = bounded
    payload_support_count = int(np.sum(support_payload_index >= 0))
    payload_candidate_count = int(np.sum(support_payload_index[slack_candidates] >= 0))
    train_accuracy = float(accuracy_score(y_train, model.predict(x_train)))

    if train_accuracy != 1.0:
        raise RuntimeError(f"training accuracy is not exact: {train_accuracy:.6f}")
    if payload_support_count != payload_bits.size:
        raise RuntimeError(
            f"payload support coverage failed: {payload_support_count}/{payload_bits.size}"
        )
    if int(np.sum(slack_candidates)) != payload_bits.size:
        raise RuntimeError(
            f"bounded support-vector count failed: {int(np.sum(slack_candidates))}/{payload_bits.size}"
        )
    if payload_candidate_count != payload_bits.size:
        raise RuntimeError(
            f"payload candidate coverage failed: {payload_candidate_count}/{payload_bits.size}"
        )

    clean_dist()
    artifact = dual_artifact_from_model(model, support_payload_index)
    with (DIST_DIR / "svc_dual_params.pkl").open("wb") as f:
        pickle.dump(artifact, f, protocol=pickle.HIGHEST_PROTOCOL)
    write_verifier(flag)
    write_requirements()

    if (DIST_DIR / "metadata.json").exists():
        raise RuntimeError("metadata.json must not be present in dist")

    solver_ok = run_solver_check(flag)
    print(f"flag length: {len(flag)}")
    print(f"payload bytes: {len(payload)}")
    print(f"payload bits: {payload_bits.size}")
    print(f"training samples: {x_train.shape[0]}")
    print(f"support vectors: {model.support_vectors_.shape[0]}")
    print(f"bounded support vectors: {int(np.sum(bounded))}")
    print(f"bounded payload candidates: {int(np.sum(slack_candidates))}")
    print(f"payload support vectors: {payload_support_count}")
    print(f"train accuracy: {train_accuracy:.6f}")
    print(f"solver check: {'pass' if solver_ok else 'fail'}")
    if not solver_ok:
        raise RuntimeError("official solver failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
