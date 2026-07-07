#!/usr/bin/env python3
"""
Bounded redteam checks for Long Khipu Braids.

This is not the intended solver. It probes for cheap public-data shortcuts:

- accidental generator leakage in dist/challenge.py,
- direct public-to-public intertwiners after decoding the SVG braid cords,
- obvious shared-key matrix candidates,
- weak matrix invariants,
- low-order public matrices.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "chall" / "generate_challenge.py"
CHALLENGE_PATH = ROOT / "dist" / "challenge.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_challenge", GENERATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {GENERATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def tag_accepts(g, matrix, p, nonce, ciphertext, tag, context) -> bool:
    key = g.derive_key(matrix, p, context)
    return hashlib.sha256(key + nonce + ciphertext).digest()[:16] == tag


def commutator(g, x, y, p):
    return g.mat_mul(
        g.mat_mul(g.mat_mul(x, y, p), g.mat_inv(x, p), p),
        g.mat_inv(y, p),
        p,
    )


def matrix_order_if_small(g, matrix, p, limit=64):
    current = g.mat_identity(len(matrix))
    for k in range(1, limit + 1):
        current = g.mat_mul(current, matrix, p)
        if g.mat_eq(current, g.mat_identity(len(matrix)), p):
            return k
    return None


def main() -> None:
    g = load_generator()
    doc = g.load_public_artifact(CHALLENGE_PATH)

    header = doc["header"]
    n = int(header["n"])
    p = int(header["p"])
    q0 = int(header.get("q0", header.get("q")))
    t0 = int(header.get("t0", header.get("t")))
    context = str(header.get("kdf_context", g.KDF_CONTEXT.decode())).encode()
    primary = doc["primary_cord"]

    print("[artifact] public generators leaked:", "generators" in primary)
    print("[artifact] public matrices leaked:", "bob_public" in primary or "alice_ephemeral" in primary)
    print("[artifact] public sections:", ", ".join(sorted(primary)))
    d = n * (n - 1) // 2
    print("[params] n,p,q,t,d:", n, p, q0, t0, d)

    Ms = g.lkb_generators(n, p, q0, t0)
    if "bob_public" in primary and "alice_ephemeral" in primary:
        Ps = g.decode_tuple_from_quipu(primary["bob_public"], p)
        Es = g.decode_tuple_from_quipu(primary["alice_ephemeral"], p)
    else:
        picture_manifest = primary["cord_pictures"]
        Ps = g.matrices_from_braid_picture_manifest(picture_manifest, "bob_public", n, Ms, p, ROOT / "dist")
        Es = g.matrices_from_braid_picture_manifest(picture_manifest, "alice_ephemeral", n, Ms, p, ROOT / "dist")
    csec = primary["ciphertext"]
    nonce = g.decimal_cords_to_bytes(csec["nonce"])
    ciphertext = g.decimal_cords_to_bytes(csec["ct"])
    tag = g.decimal_cords_to_bytes(csec["tag"])

    print("[cipher] lengths nonce/ct/tag:", len(nonce), len(ciphertext), len(tag))
    print("[rng] nonce exposes 128 bits; MT19937 state recovery needs 624 32-bit outputs")

    passing = []
    simple_candidates = {
        "identity": g.mat_identity(d),
        "M_1": Ms[0],
        "P_1": Ps[0],
        "E_1": Es[0],
    }

    for name, matrix in simple_candidates.items():
        if tag_accepts(g, matrix, p, nonce, ciphertext, tag, context):
            passing.append(name)

    y, nullity, rows, rank = g.recover_conjugator(Ps, Es, p)
    print("[direct-intertwiner] P->E nullity/rank/rows:", nullity, rank, rows)
    direct_candidates = {
        "Y_public_to_public": y,
        "Y_inverse": g.mat_inv(y, p),
    }
    for i, (pmat, emat) in enumerate(zip(Ps, Es), start=1):
        direct_candidates[f"[Y,P_{i}]"] = commutator(g, y, pmat, p)
        direct_candidates[f"[Y,E_{i}]"] = commutator(g, y, emat, p)
    for name, matrix in direct_candidates.items():
        if tag_accepts(g, matrix, p, nonce, ciphertext, tag, context):
            passing.append(name)

    print("[candidate-keys] simple/direct candidates passing tag:", passing or "none")

    dets_m = [g.mat_det(m, p) for m in Ms]
    dets_p = [g.mat_det(m, p) for m in Ps]
    dets_e = [g.mat_det(m, p) for m in Es]
    print("[invariants] det(M_i)==det(P_i)==det(E_i):", dets_m == dets_p == dets_e)
    print("[invariants] first generator determinant:", dets_m[0])
    print("[invariants] gcd(28, p-1):", math.gcd(d, p - 1))

    small_orders = []
    for family, mats in (("M", Ms), ("P", Ps), ("E", Es)):
        for i, matrix in enumerate(mats, start=1):
            order = matrix_order_if_small(g, matrix, p, limit=64)
            if order is not None:
                small_orders.append(f"{family}_{i}:{order}")
    print("[orders] public/generator matrix orders <=64:", small_orders or "none")

    print("[summary] no checked shortcut recovered the flag")


if __name__ == "__main__":
    main()
