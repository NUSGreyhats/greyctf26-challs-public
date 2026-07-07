#!/usr/bin/env sage
from operator import xor
from sage.all import Matrix, ZZ, inverse_mod
from sage.modules.free_module_integer import IntegerLattice

import cmath
import hashlib
import json
import re
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_PATH = ROOT / "dist" / "output.json"
TOP_PEAKS_PER_BLOCK = int(4)
SUBSTITUTION_BLOCKS = int(8)


def xor_bytes(a, b):
    return bytes(xor(x, y) for x, y in zip(a, b))


def stream_for_sk(sk, nbytes):
    label = ("nothing to see here:" + str(sk)).encode()
    return hashlib.shake_256(label).digest(nbytes)


def decrypt_with_sk(candidate, ciphertext):
    stream = stream_for_sk(candidate, len(ciphertext))
    return xor_bytes(ciphertext, stream)


def round_grid_point(j, q, L):
    return ((int(j) * q) + (L // 2)) // L % q


def block_fft_peaks(block, q, L):
    # Reduced coefficients are bounded by L, so the bias polynomial fits in an
    # L-point FFT array. The z_i phase is independent of the candidate key.
    A = np.zeros(L, dtype=np.complex128)
    q_float = float(q)
    for a, z in block["samples"]:
        A[int(a)] += cmath.exp(2j * np.pi * (float(int(z)) / q_float))

    # np.fft.ifft(A) * L computes:
    #   sum_a A[a] * exp(+2*pi*i*a*j/L)
    # which approximates sum_i exp(2*pi*i*(z_i+a_i*(j*q/L))/q).
    S = np.fft.ifft(A) * L
    scores = np.abs(S)

    # Keep several peaks per block. The top peak should be correct, but using a
    # few alternatives makes the reference solver robust to unlucky noise.
    top_count = min(TOP_PEAKS_PER_BLOCK, L)
    peak_idx = np.argpartition(scores, -top_count)[-top_count:]
    peak_idx = sorted((int(j) for j in peak_idx), key=lambda j: scores[j], reverse=True)
    peaks = [
        {
            "j": j,
            "center": round_grid_point(j, q, L),
            "score": float(scores[j]),
        }
        for j in peak_idx
    ]
    margin = peaks[0]["score"] / max(peaks[1]["score"], 1e-12)
    return peaks, margin


def lattice_rows(rs, q):
    # Row lattice:
    #   (r_0*x + q*m_0, ..., r_{T-1}*x + q*m_{T-1})
    # for integers x,m_i. The closest vector to c=(c_t) should use x=sk.
    rows = [list(map(int, rs))]
    for i in range(len(rs)):
        row = [int(0)] * len(rs)
        row[i] = q
        rows.append(row)
    return rows


def sk_from_lattice_vector(v, rs, q):
    # For a valid closest vector v_i = r_i*sk mod q in every coordinate. Recover
    # sk from each coordinate and require unanimous agreement.
    recovered = []
    for vi, ri in zip(v, rs):
        recovered.append((int(vi) * int(inverse_mod(int(ri), q))) % q)
    if len(set(recovered)) != 1:
        return None
    sk = recovered[0]
    if not (int(1) <= sk < q):
        return None
    return sk


def recover_with_sage_approx(rs, centers, q):
    # Sage's approximate closest-vector routine is enough for this low
    # dimension and avoids the expensive exact native closest_vector path.
    B = Matrix(ZZ, lattice_rows(rs, q))
    lattice = IntegerLattice(B)
    v = lattice.approximate_closest_vector(list(map(int, centers)))
    return sk_from_lattice_vector(v, rs, q)


def recover_with_fpylll(rs, centers, q):
    from fpylll import CVP, LLL, IntegerMatrix

    # Fallback exact CVP path. HNF converts the rectangular generating set into
    # a square full-rank basis for the same row lattice before fpylll reduction.
    B = Matrix(ZZ, lattice_rows(rs, q))
    H = B.hermite_form()
    basis = [
        list(map(int, H.row(i)))
        for i in range(H.nrows())
        if any(H[i, j] for j in range(H.ncols()))
    ]
    A = IntegerMatrix.from_matrix(basis)
    LLL.reduction(A)
    v = CVP.closest_vector(A, list(map(int, centers)))
    return sk_from_lattice_vector(v, rs, q)


def candidate_center_sets(peaks_by_block, margins):
    top_centers = [peaks[0]["center"] for peaks in peaks_by_block]
    yield "all top peaks", top_centers

    # If the all-top-peak solve fails, retry one substitution at a time in the
    # noisiest blocks. This keeps the search tiny: 1 + 8*(4-1) CVP attempts.
    weak_blocks = sorted(range(len(margins)), key=lambda idx: margins[idx])[:SUBSTITUTION_BLOCKS]
    for block_idx in weak_blocks:
        for alt_idx, peak in enumerate(peaks_by_block[block_idx][1:], start=int(2)):
            centers = list(top_centers)
            centers[block_idx] = peak["center"]
            yield f"block {block_idx} peak {alt_idx}", centers


def recover_candidates(rs, centers, q):
    candidates = []
    sk = recover_with_sage_approx(rs, centers, q)
    if sk is not None:
        candidates.append((sk, "Sage approximate CVP"))

    sk = recover_with_fpylll(rs, centers, q)
    if sk is not None and all(sk != existing for existing, _ in candidates):
        candidates.append((sk, "fpylll exact CVP"))

    return candidates


def main():
    with PUBLIC_PATH.open("r") as f:
        data = json.load(f)

    q = int(data["q"])
    L = int(data["L"])
    T = int(data["T"])
    M_per_block = int(data["M_per_block"])
    blocks = data["blocks"]
    ciphertext = bytes.fromhex(data["ciphertext_hex"])
    assert len(blocks) == T
    assert all(len(block["samples"]) == M_per_block for block in blocks)

    print(f"[+] loaded {T} blocks, {T * M_per_block} samples")
    print(f"[+] q has {q.bit_length()} bits, L = {L}, q//L has {(q // L).bit_length()} bits")

    rs = []
    peaks_by_block = []
    margins = []
    for t, block in enumerate(blocks):
        r = int(block["r"])
        rs.append(r)
        peaks, margin = block_fft_peaks(block, q, L)
        peaks_by_block.append(peaks)
        margins.append(margin)
        print(
            f"[+] block {t:02d}: top j = {peaks[0]['j']}, "
            f"score = {peaks[0]['score']:.2f}, top1/top2 = {margin:.3f}"
        )

    # The solve does not brute force the q/L-sized bin. CVP combines all block
    # centers into one 20-dimensional bounded-distance instance.
    for label, centers in candidate_center_sets(peaks_by_block, margins):
        print(f"[+] trying CVP with {label}")
        candidates = recover_candidates(rs, centers, q)
        if not candidates:
            print("[-] no CVP method recovered a consistent key")
            continue

        for sk, method in candidates:
            plaintext = decrypt_with_sk(sk, ciphertext)
            if re.fullmatch(rb"grey\{.*\}", plaintext):
                print(f"[+] CVP method = {method}")
                print(f"[+] recovered sk = {sk}")
                print(f"[+] recovered flag = {plaintext.decode()}")
                return
        print("[-] CVP candidates did not decrypt to the flag format")

    raise RuntimeError("failed to recover the flag from the checked peak combinations")


if __name__ == "__main__":
    main()
