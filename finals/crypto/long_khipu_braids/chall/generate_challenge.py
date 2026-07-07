#!/usr/bin/env python3
"""
Long Khipu Braids v4.0 hard-mode CTF system and linear-algebra exploit.

Pure Python, no Sage dependency.  It implements the Bigelow convention for the
Lawrence-Krammer-Bigelow generator matrices over GF(p), then builds the toy
conjugacy-KEM described in the writeup.

Run:
    python3 chall/generate_challenge.py
    python3 chall/generate_challenge.py --solve-only dist/challenge.py
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import random
import argparse
import html
import os
import re
import runpy
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple, Optional

Matrix = List[List[int]]
Vector = List[int]


DEFAULT_N = 8
DEFAULT_P = 10_000_019  # prime
DEFAULT_Q0 = 17
DEFAULT_T0 = 42
DEFAULT_WORD_LENGTH = 96
DEFAULT_SEED = 20260524
DEFAULT_FLAG = b"grey{kn0t5_BiNd_s3CreTs_w1Th0Ut_w0rdZ_0ops_1_t1nK_i_Ti3D_mY_h4Ndz_2gether...}"
DEFAULT_OUTPUT = str(Path(__file__).resolve().parents[1] / "dist" / "challenge.py")
DEFAULT_CORD_DIR = str(Path(__file__).resolve().parents[1] / "dist" / "cords")
KDF_CONTEXT = b"Long-Khipu-Braids-v4.0"


# --------------------------- finite-field matrix code ---------------------------

def mod(x: int, p: int) -> int:
    return x % p


def inv_mod(a: int, p: int) -> int:
    a %= p
    if a == 0:
        raise ZeroDivisionError("division by zero in GF(p)")
    return pow(a, -1, p)


def mat_zero(r: int, c: int) -> Matrix:
    return [[0 for _ in range(c)] for _ in range(r)]


def mat_identity(n: int) -> Matrix:
    I = mat_zero(n, n)
    for i in range(n):
        I[i][i] = 1
    return I


def mat_shape(A: Matrix) -> Tuple[int, int]:
    return len(A), len(A[0]) if A else 0


def mat_mul(A: Matrix, B: Matrix, p: int) -> Matrix:
    ar, ac = mat_shape(A)
    br, bc = mat_shape(B)
    assert ac == br
    C = mat_zero(ar, bc)
    for i in range(ar):
        Ai = A[i]
        for k in range(ac):
            aik = Ai[k]
            if aik:
                Bk = B[k]
                for j in range(bc):
                    C[i][j] = (C[i][j] + aik * Bk[j]) % p
    return C


def mat_add(A: Matrix, B: Matrix, p: int) -> Matrix:
    r, c = mat_shape(A)
    return [[(A[i][j] + B[i][j]) % p for j in range(c)] for i in range(r)]


def mat_sub(A: Matrix, B: Matrix, p: int) -> Matrix:
    r, c = mat_shape(A)
    return [[(A[i][j] - B[i][j]) % p for j in range(c)] for i in range(r)]


def mat_eq(A: Matrix, B: Matrix, p: int) -> bool:
    if mat_shape(A) != mat_shape(B):
        return False
    r, c = mat_shape(A)
    return all((A[i][j] - B[i][j]) % p == 0 for i in range(r) for j in range(c))


def mat_pow(A: Matrix, e: int, p: int) -> Matrix:
    n, m = mat_shape(A)
    assert n == m
    if e < 0:
        return mat_pow(mat_inv(A, p), -e, p)
    R = mat_identity(n)
    B = A
    while e:
        if e & 1:
            R = mat_mul(R, B, p)
        B = mat_mul(B, B, p)
        e >>= 1
    return R


def mat_inv(A: Matrix, p: int) -> Matrix:
    n, m = mat_shape(A)
    assert n == m
    aug = [row[:] + ident for row, ident in zip(A, mat_identity(n))]
    col = 0
    for col in range(n):
        pivot = None
        for r in range(col, n):
            if aug[r][col] % p:
                pivot = r
                break
        if pivot is None:
            raise ValueError("matrix is singular")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        inv_piv = inv_mod(aug[col][col], p)
        aug[col] = [(x * inv_piv) % p for x in aug[col]]
        for r in range(n):
            if r == col:
                continue
            factor = aug[r][col] % p
            if factor:
                aug[r] = [(aug[r][j] - factor * aug[col][j]) % p for j in range(2 * n)]
    return [row[n:] for row in aug]


def mat_det(A: Matrix, p: int) -> int:
    n, m = mat_shape(A)
    assert n == m
    M = [row[:] for row in A]
    det = 1
    for c in range(n):
        pivot = None
        for r in range(c, n):
            if M[r][c] % p:
                pivot = r
                break
        if pivot is None:
            return 0
        if pivot != c:
            M[c], M[pivot] = M[pivot], M[c]
            det = -det
        piv = M[c][c] % p
        det = (det * piv) % p
        inv_piv = inv_mod(piv, p)
        for r in range(c + 1, n):
            factor = (M[r][c] * inv_piv) % p
            if factor:
                for j in range(c, n):
                    M[r][j] = (M[r][j] - factor * M[c][j]) % p
    return det % p


def rref(M: Matrix, p: int) -> Tuple[Matrix, List[int]]:
    """Reduced row echelon form over GF(p), with pivot columns."""
    A = [row[:] for row in M]
    rows = len(A)
    cols = len(A[0]) if rows else 0
    pivots: List[int] = []
    r = 0
    for c in range(cols):
        pivot = None
        for rr in range(r, rows):
            if A[rr][c] % p:
                pivot = rr
                break
        if pivot is None:
            continue
        A[r], A[pivot] = A[pivot], A[r]
        inv_piv = inv_mod(A[r][c], p)
        A[r] = [(x * inv_piv) % p for x in A[r]]
        for rr in range(rows):
            if rr == r:
                continue
            factor = A[rr][c] % p
            if factor:
                A[rr] = [(A[rr][j] - factor * A[r][j]) % p for j in range(cols)]
        pivots.append(c)
        r += 1
        if r == rows:
            break
    return A, pivots


def nullspace(M: Matrix, p: int) -> List[Vector]:
    """Basis for the right nullspace of M over GF(p)."""
    if not M:
        return []
    R, pivots = rref(M, p)
    cols = len(M[0])
    pivot_set = set(pivots)
    free_cols = [c for c in range(cols) if c not in pivot_set]
    basis: List[Vector] = []
    for fc in free_cols:
        v = [0] * cols
        v[fc] = 1
        for row, pc in enumerate(pivots):
            # R[row][pc] = 1, so x_pc + sum free R[row][free]*x_free = 0
            v[pc] = (-R[row][fc]) % p
        basis.append(v)
    return basis


# --------------------------- LKB representation ---------------------------

def lkb_basis(n: int) -> List[Tuple[int, int]]:
    return [(j, k) for j in range(1, n + 1) for k in range(j + 1, n + 1)]


def lkb_generators(n: int, p: int, q0: int, t0: int) -> List[Matrix]:
    """
    Return [rho(sigma_1), ..., rho(sigma_{n-1})] over GF(p).

    Convention: basis vectors are v_{j,k}, 1 <= j < k <= n, lexicographically.
    The matrix columns are images of basis vectors. Formula is Bigelow's
    Sage-compatible Bigelow convention.
    """
    q = q0 % p
    t = t0 % p
    q2_minus_q = (q * q - q) % p
    basis = lkb_basis(n)
    index: Dict[Tuple[int, int], int] = {pair: idx for idx, pair in enumerate(basis)}
    d = len(basis)
    gens: List[Matrix] = []

    def add(coeffs: Dict[Tuple[int, int], int], pair: Tuple[int, int], coeff: int):
        assert pair[0] < pair[1], pair
        coeffs[pair] = (coeffs.get(pair, 0) + coeff) % p

    for i in range(1, n):
        M = mat_zero(d, d)
        for col, (j, k) in enumerate(basis):
            coeffs: Dict[Tuple[int, int], int] = {}
            if i == j and i == k - 1:
                # i = j = k - 1
                add(coeffs, (j, k), -t * q * q)
            elif i not in {j - 1, j, k - 1, k}:
                add(coeffs, (j, k), 1)
            elif i == j - 1:
                add(coeffs, (i, k), q)
                add(coeffs, (i, j), q2_minus_q)
                add(coeffs, (j, k), 1 - q)
            elif i == j and i != k - 1:
                add(coeffs, (j + 1, k), 1)
            elif i == k - 1 and i != j:
                add(coeffs, (j, i), q)
                add(coeffs, (j, k), 1 - q)
                add(coeffs, (i, k), (1 - q) * q * t)
            elif i == k:
                add(coeffs, (j, k + 1), 1)
            else:
                raise AssertionError(f"unhandled case i={i}, j={j}, k={k}")
            for pair, coeff in coeffs.items():
                M[index[pair]][col] = coeff % p
        gens.append(M)
    return gens


def braid_matrix(word: Sequence[int], gens: Sequence[Matrix], p: int) -> Matrix:
    """
    Convert a braid word into a product of LKB generator matrices.
    Positive integer i means sigma_i; negative -i means sigma_i^-1.
    """
    d = len(gens[0])
    M = mat_identity(d)
    inv_cache: Dict[int, Matrix] = {}
    for s in word:
        idx = abs(s) - 1
        if idx < 0 or idx >= len(gens):
            raise ValueError(f"bad generator index in word: {s}")
        G = gens[idx]
        if s < 0:
            if idx not in inv_cache:
                inv_cache[idx] = mat_inv(G, p)
            G = inv_cache[idx]
        M = mat_mul(M, G, p)
    return M


def conjugate_tuple(X: Matrix, gens: Sequence[Matrix], p: int) -> List[Matrix]:
    Xinv = mat_inv(X, p)
    return [mat_mul(mat_mul(X, M, p), Xinv, p) for M in gens]


# --------------------------- linear exploit ---------------------------

def build_intertwiner_system(Ms: Sequence[Matrix], Ps: Sequence[Matrix], p: int) -> Matrix:
    """
    Build linear equations for X M_i = P_i X.

    Unknown order is row-major: x_{0,0}, x_{0,1}, ..., x_{d-1,d-1}.
    For each equation (r,c): sum_k X[r,k] M[k,c] - sum_k P[r,k] X[k,c] = 0.
    """
    d = len(Ms[0])
    rows: Matrix = []
    for M, P in zip(Ms, Ps):
        for r in range(d):
            for c in range(d):
                eq = [0] * (d * d)
                for k in range(d):
                    # X[r,k] * M[k,c]
                    eq[r * d + k] = (eq[r * d + k] + M[k][c]) % p
                    # - P[r,k] * X[k,c]
                    eq[k * d + c] = (eq[k * d + c] - P[r][k]) % p
                rows.append(eq)
    return rows


def vector_to_matrix_row_major(v: Vector, d: int) -> Matrix:
    return [v[r * d:(r + 1) * d] for r in range(d)]


def iter_intertwiner_rows_round_robin(Ms: Sequence[Matrix], Ps: Sequence[Matrix], p: int) -> Iterable[Vector]:
    """
    Yield equations for X M_i = P_i X without materializing the whole system.

    The order deliberately interleaves generators for each matrix coordinate. This
    tends to expose independent equations early, so the solver can stop as soon
    as the nullspace is one-dimensional.
    """
    d = len(Ms[0])
    for r in range(d):
        for c in range(d):
            for M, P in zip(Ms, Ps):
                eq = [0] * (d * d)
                for k in range(d):
                    # X[r,k] * M[k,c]
                    eq[r * d + k] = (eq[r * d + k] + M[k][c]) % p
                    # - P[r,k] * X[k,c]
                    eq[k * d + c] = (eq[k * d + c] - P[r][k]) % p
                yield eq


def one_dimensional_nullspace_incremental(
    rows: Iterable[Vector],
    ncols: int,
    p: int,
    target_nullity: int = 1,
) -> Tuple[List[Vector], int, int]:
    """
    Incremental RREF over GF(p), stopping once rank = ncols-target_nullity.

    The full intertwiner system often has thousands of rows. For these challenge
    instances we only need the one-dimensional nullspace, so processing every row
    is unnecessary once enough independent constraints have been seen.
    """
    target_rank = ncols - target_nullity
    pivots: List[int] = []
    pivot_rows: Dict[int, Vector] = {}
    processed = 0

    for row in rows:
        processed += 1

        # Reduce the candidate row by the current RREF pivot rows.
        for pc in pivots:
            coeff = row[pc] % p
            if coeff:
                prow = pivot_rows[pc]
                for j in range(pc, ncols):
                    row[j] = (row[j] - coeff * prow[j]) % p

        # Find the new pivot.
        pc_new: Optional[int] = None
        for j, x in enumerate(row):
            if x % p:
                pc_new = j
                break
        if pc_new is None:
            continue

        inv_piv = inv_mod(row[pc_new], p)
        row = [(x * inv_piv) % p for x in row]

        # Maintain RREF by clearing the new pivot column in old pivot rows.
        for pc_old in pivots:
            prow = pivot_rows[pc_old]
            coeff = prow[pc_new] % p
            if coeff:
                for j in range(pc_new, ncols):
                    prow[j] = (prow[j] - coeff * row[j]) % p

        pivot_rows[pc_new] = row
        pivots.append(pc_new)
        pivots.sort()

        if len(pivots) >= target_rank:
            break

    free_cols = [c for c in range(ncols) if c not in pivot_rows]
    basis: List[Vector] = []
    for fc in free_cols:
        v = [0] * ncols
        v[fc] = 1
        for pc in pivots:
            v[pc] = (-pivot_rows[pc][fc]) % p
        basis.append(v)
    return basis, processed, len(pivots)


def recover_conjugator(Ms: Sequence[Matrix], Ps: Sequence[Matrix], p: int) -> Tuple[Matrix, int, int, int]:
    """
    Recover X up to nonzero scalar from P_i = X M_i X^-1.

    Returns (X, nullity, rows_processed, rank). The usual hardened instance has
    nullity=1. The incremental solver stops once it has enough independent rows;
    a full nullspace fallback is retained for odd parameter choices.
    """
    d = len(Ms[0])
    ncols = d * d

    ns, processed, rank = one_dimensional_nullspace_incremental(
        iter_intertwiner_rows_round_robin(Ms, Ps, p),
        ncols,
        p,
        target_nullity=1,
    )

    for v in ns:
        X = vector_to_matrix_row_major(v, d)
        if mat_det(X, p) != 0 and all(mat_eq(mat_mul(X, M, p), mat_mul(P, X, p), p) for M, P in zip(Ms, Ps)):
            return X, len(ns), processed, rank

    # Fallback: materialize the full system and compute the full right kernel.
    system = build_intertwiner_system(Ms, Ps, p)
    ns = nullspace(system, p)
    candidates = ns[:]
    rng = random.Random(1337)
    if len(ns) > 1:
        for _ in range(300):
            coeffs = [rng.randrange(p) for _ in ns]
            if all(c == 0 for c in coeffs):
                continue
            v = [0] * ncols
            for c, b in zip(coeffs, ns):
                if c:
                    v = [(vv + c * bb) % p for vv, bb in zip(v, b)]
            candidates.append(v)
    for v in candidates:
        X = vector_to_matrix_row_major(v, d)
        if mat_det(X, p) != 0:
            assert all(mat_eq(mat_mul(X, M, p), mat_mul(P, X, p), p) for M, P in zip(Ms, Ps))
            return X, len(ns), len(system), ncols - len(ns)
    raise ValueError(f"no invertible conjugator found; nullity={len(ns)}")


# --------------------------- quipu-style serialization ---------------------------

def decimal_digits_fixed(x: int, width: int) -> List[int]:
    s = str(x).zfill(width)
    return [int(ch) for ch in reversed(s)]  # units first, quipu-style low register first


def integer_from_digits_fixed(digits_units_first: Sequence[int]) -> int:
    return sum(d * (10 ** i) for i, d in enumerate(digits_units_first))


def encode_field_element_as_knots(x: int, p: int) -> Dict[str, object]:
    """
    Machine-readable knot registers. This is intentionally verbose so the parser
    is obvious. A physical/artistic version would draw these as knots on an entry cord.
    """
    width = len(str(p - 1))
    x %= p
    digits = decimal_digits_fixed(x, width)
    return {
        "cord": "entry",
        "presence_knot": True,
        "base": 10,
        "registers_low_to_high": [
            {"power": j, "turns": d} for j, d in enumerate(digits)
        ],
    }


def decode_field_element_from_knots(obj: Dict[str, object], p: int) -> int:
    regs = obj["registers_low_to_high"]
    digits = [int(reg["turns"]) for reg in regs]
    x = integer_from_digits_fixed(digits)
    if not (0 <= x < p):
        raise ValueError(f"decoded field element {x} not in GF({p})")
    return x


def encode_matrix_as_quipu(Y: Matrix, p: int, label: str) -> Dict[str, object]:
    return {
        "cord": "matrix",
        "label": label,
        "rows": [
            {
                "cord": "row",
                "row_index": r,
                "entries": [encode_field_element_as_knots(x, p) for x in row],
            }
            for r, row in enumerate(Y)
        ],
    }


def decode_matrix_from_quipu(obj: Dict[str, object], p: int) -> Matrix:
    return [
        [decode_field_element_from_knots(entry, p) for entry in row["entries"]]
        for row in obj["rows"]
    ]


def encode_tuple_as_quipu(mats: Sequence[Matrix], p: int, section: str, prefix: str) -> Dict[str, object]:
    return {
        "cord": "section",
        "section": section,
        "matrices": [encode_matrix_as_quipu(M, p, f"{prefix}_{i+1}") for i, M in enumerate(mats)],
    }


def decode_tuple_from_quipu(obj: Dict[str, object], p: int) -> List[Matrix]:
    return [decode_matrix_from_quipu(mobj, p) for mobj in obj["matrices"]]


def bytes_to_decimal_cords(data: bytes) -> List[Dict[str, object]]:
    # Field p is not relevant here; use width 3 because bytes are 0..255.
    cords = []
    for b in data:
        digits = decimal_digits_fixed(b, 3)
        cords.append({
            "cord": "byte",
            "presence_knot": True,
            "base": 10,
            "registers_low_to_high": [{"power": j, "turns": d} for j, d in enumerate(digits)],
        })
    return cords


def decimal_cords_to_bytes(cords: Sequence[Dict[str, object]]) -> bytes:
    out = []
    for c in cords:
        x = integer_from_digits_fixed([int(reg["turns"]) for reg in c["registers_low_to_high"]])
        if not (0 <= x <= 255):
            raise ValueError(f"bad byte value: {x}")
        out.append(x)
    return bytes(out)


# --------------------------- braid-picture artifacts ---------------------------

STRAND_COLORS = [
    "#355C7D", "#C06C84", "#2A9D8F", "#E9C46A",
    "#7A5195", "#EF5675", "#1F77B4", "#8C6D31",
]


def svg_path_segment(x0: float, y0: float, x1: float, y1: float) -> str:
    dy = y1 - y0
    return f"M {x0:.1f} {y0:.1f} C {x0:.1f} {y0 + 0.45 * dy:.1f}, {x1:.1f} {y0 + 0.55 * dy:.1f}, {x1:.1f} {y1:.1f}"


def write_braid_svg(word: Sequence[int], n: int, label: str, path: Path) -> None:
    lane_gap = 42
    margin_x = 62
    top = 76
    step = 18
    bottom = top + step * (len(word) + 1)
    width = margin_x * 2 + lane_gap * (n - 1)
    height = bottom + 58
    stroke = 5

    def x_for_lane(lane: int) -> float:
        return margin_x + lane * lane_gap

    def side_register_knots(crossing_number: int, cy: float) -> str:
        if crossing_number % 10 == 0:
            knots = []
            for offset in (-5.5, 0.0, 5.5):
                knots.append(f'<ellipse cx="24" cy="{cy + offset:.1f}" rx="4.5" ry="2.5" class="register-knot"/>')
            return "".join(knots)
        if crossing_number % 5 == 0:
            return f'<ellipse cx="24" cy="{cy:.1f}" rx="4.0" ry="2.8" class="register-knot"/>'
        return f'<circle cx="24" cy="{cy:.1f}" r="2.0" class="register-knot"/>'

    lane_to_strand = list(range(n))
    pieces: List[str] = []

    # Top labels and a khipu-like header cord.
    pieces.append(f'<text x="{width / 2:.1f}" y="32" text-anchor="middle" class="title">{html.escape(label)}</text>')
    pieces.append(f'<line x1="28" y1="48" x2="{width - 28}" y2="48" class="header"/>')
    for lane in range(n):
        x = x_for_lane(lane)
        color = STRAND_COLORS[lane % len(STRAND_COLORS)]
        pieces.append(f'<circle cx="{x:.1f}" cy="48" r="6" fill="{color}"/>')
        pieces.append(f'<text x="{x:.1f}" y="64" text-anchor="middle" class="strand-label">{lane + 1}</text>')

    y = top
    for crossing_number, s in enumerate(word, start=1):
        crossing_lane = abs(s) - 1
        if not (0 <= crossing_lane < n - 1):
            raise ValueError(f"bad braid generator {s}")
        y_next = y + step

        for lane, strand in enumerate(lane_to_strand):
            if lane not in {crossing_lane, crossing_lane + 1}:
                x = x_for_lane(lane)
                color = STRAND_COLORS[strand % len(STRAND_COLORS)]
                pieces.append(f'<path d="M {x:.1f} {y:.1f} L {x:.1f} {y_next:.1f}" stroke="{color}" class="strand"/>')

        left_strand = lane_to_strand[crossing_lane]
        right_strand = lane_to_strand[crossing_lane + 1]
        left_path = svg_path_segment(x_for_lane(crossing_lane), y, x_for_lane(crossing_lane + 1), y_next)
        right_path = svg_path_segment(x_for_lane(crossing_lane + 1), y, x_for_lane(crossing_lane), y_next)

        over_is_left = s > 0
        under_path, under_strand = (right_path, right_strand) if over_is_left else (left_path, left_strand)
        over_path, over_strand = (left_path, left_strand) if over_is_left else (right_path, right_strand)

        pieces.append(
            f'<g class="crossing">'
            f'{side_register_knots(crossing_number, (y + y_next) / 2)}'
            f'<path d="{under_path}" stroke="{STRAND_COLORS[under_strand % len(STRAND_COLORS)]}" class="strand"/>'
            f'<path d="{over_path}" stroke="{STRAND_COLORS[over_strand % len(STRAND_COLORS)]}" class="strand"/>'
            f'</g>'
        )

        lane_to_strand[crossing_lane], lane_to_strand[crossing_lane + 1] = (
            lane_to_strand[crossing_lane + 1],
            lane_to_strand[crossing_lane],
        )
        y = y_next

    for lane, strand in enumerate(lane_to_strand):
        x = x_for_lane(lane)
        color = STRAND_COLORS[strand % len(STRAND_COLORS)]
        pieces.append(f'<path d="M {x:.1f} {y:.1f} L {x:.1f} {bottom:.1f}" stroke="{color}" class="strand"/>')
        pieces.append(f'<circle cx="{x:.1f}" cy="{bottom + 16:.1f}" r="5" fill="{color}"/>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(label)} crossing cord">
<style>
  svg {{ background: #fbfaf6; }}
  .title {{ font: 700 18px ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #222; }}
  .strand-label {{ font: 11px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; fill: #555; }}
  .header {{ stroke: #4a3b2a; stroke-width: 4; stroke-linecap: round; }}
  .register-knot {{ fill: #4a3b2a; }}
  .strand {{ fill: none; stroke-width: {stroke}; stroke-linecap: round; }}
</style>
{chr(10).join(pieces)}
</svg>
'''
    path.write_text(svg, encoding="utf-8")


def relative_artifact_path(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return os.path.relpath(path, base)


def write_braid_gallery(manifest: Dict[str, List[Dict[str, object]]], output_path: Path) -> None:
    sections = []
    for section, pictures in manifest.items():
        cards = []
        for picture in pictures:
            label = html.escape(str(picture["label"]))
            file_name = html.escape(str(picture["file"]))
            cards.append(f'<figure><a href="{file_name}"><img src="{file_name}" alt="{label}"></a><figcaption>{label}</figcaption></figure>')
        sections.append(f'<section><h2>{html.escape(section)}</h2><div class="grid">{"".join(cards)}</div></section>')

    page = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Long Khipu Braids transcript</title>
<style>
  body {{ margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #222; background: #fbfaf6; }}
  main {{ max-width: 1120px; margin: 0 auto; padding: 28px 18px 48px; }}
  h1 {{ margin: 0 0 8px; font-size: 28px; }}
  p {{ max-width: 760px; line-height: 1.45; }}
  h2 {{ margin-top: 30px; font-size: 20px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }}
  figure {{ margin: 0; border: 1px solid #d6d0c4; background: #fffdf8; border-radius: 6px; overflow: hidden; }}
  img {{ width: 100%; max-height: 720px; object-fit: contain; object-position: top center; display: block; background: #fbfaf6; }}
  figcaption {{ padding: 8px 10px; font: 600 13px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
</style>
</head>
<body>
<main>
<h1>Long Khipu Braids transcript</h1>
<p>The public exchange is recorded as khipu crossing cords. Bob publishes one cord for each base crossing, Alice replies with the matching ephemeral cords, and the sealed cord contains the nonce, ciphertext, and tag.</p>
{chr(10).join(sections)}
</main>
</body>
</html>
'''
    output_path.write_text(page, encoding="utf-8")


def _svg_path_endpoints(d: str) -> Tuple[float, float, float, float]:
    nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", d)]
    if len(nums) < 8:
        raise ValueError(f"cannot parse SVG path: {d!r}")
    return nums[0], nums[1], nums[-2], nums[-1]


def read_braid_svg_word(path: Path, n: int) -> List[int]:
    """
    Recover the Artin word from one generated SVG.

    This intentionally reads only the visible geometry and paint order:
    the topmost strand at a crossing is drawn after the lower strand.
    """
    root = ET.parse(path).getroot()
    lane_gap = 42.0
    margin_x = 62.0
    word: List[Tuple[float, int]] = []
    for elem in root.iter():
        if "crossing" not in elem.attrib.get("class", "").split():
            continue
        paths = [child for child in list(elem) if child.tag.endswith("path")]
        if len(paths) != 2:
            raise ValueError(f"unexpected crossing shape in {path}")
        over = paths[1]
        x0, y0, x1, _ = _svg_path_endpoints(over.attrib["d"])
        lane = round((min(x0, x1) - margin_x) / lane_gap)
        if not (0 <= lane < n - 1):
            raise ValueError(f"decoded bad crossing lane {lane + 1} in {path}")
        sign = 1 if x0 < x1 else -1
        word.append((y0, sign * (lane + 1)))
    return [s for _, s in sorted(word)]


def write_public_cord_pictures(chal: Challenge, output_dir: Path, base_dir: Path) -> Dict[str, List[Dict[str, object]]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    words_by_section = public_picture_words(chal)
    expected = {
        "bob_public": chal.bob_public,
        "alice_ephemeral": chal.alice_ephemeral,
    }
    prefixes = {
        "bob_public": "P",
        "alice_ephemeral": "E",
    }
    manifest: Dict[str, List[Dict[str, object]]] = {}
    for section, words in words_by_section.items():
        public_section = "bob" if section == "bob_public" else "alice"
        manifest[public_section] = []
        for i, word in enumerate(words, start=1):
            M = braid_matrix(word, chal.generators, chal.p)
            if not mat_eq(M, expected[section][i - 1], chal.p):
                raise AssertionError(f"scrambled {section}_{i} changed the public braid")
            label = f"{prefixes[section]}_{i}"
            path = output_dir / f"{public_section}_{label}.svg"
            write_braid_svg(word, chal.n, label, path)
            manifest[public_section].append({
                "label": label,
                "file": relative_artifact_path(path, base_dir),
                "crossings": len(word),
            })
    write_braid_gallery(manifest, base_dir / "exchange.html")
    return manifest


def matrices_from_braid_picture_manifest(
    manifest: Dict[str, object],
    section: str,
    n: int,
    gens: Sequence[Matrix],
    p: int,
    base_dir: Path,
) -> List[Matrix]:
    public_section = {"bob_public": "bob", "alice_ephemeral": "alice"}.get(section, section)
    pictures = manifest["pictures"][public_section]
    mats: List[Matrix] = []
    for picture in pictures:
        svg_path = base_dir / str(picture["file"])
        word = read_braid_svg_word(svg_path, n)
        if "crossings" in picture and len(word) != int(picture["crossings"]):
            raise ValueError(f"crossing count mismatch for {svg_path}")
        mats.append(braid_matrix(word, gens, p))
    return mats


# --------------------------- KEM + symmetric wrapper ---------------------------

def matrix_to_bytes(M: Matrix, p: int) -> bytes:
    width = (p.bit_length() + 7) // 8
    return b"".join(int(x % p).to_bytes(width, "big") for row in M for x in row)


def derive_key(K: Matrix, p: int, context: bytes = KDF_CONTEXT) -> bytes:
    return hashlib.sha256(context + matrix_to_bytes(K, p)).digest()


def xor_shake256(key: bytes, nonce: bytes, data: bytes) -> bytes:
    stream = hashlib.shake_256(key + nonce).digest(len(data))
    return bytes(a ^ b for a, b in zip(data, stream))


def random_braid_word(n: int, length: int, rng: random.Random) -> List[int]:
    # Avoid immediately cancelling adjacent letters, mostly for aesthetics.
    word: List[int] = []
    while len(word) < length:
        g = rng.randint(1, n - 1)
        s = g if rng.choice([False, True]) else -g
        if word and word[-1] == -s:
            continue
        word.append(s)
    return word


def inverse_braid_word(word: Sequence[int]) -> List[int]:
    return [-s for s in reversed(word)]


def public_conjugate_words(secret_word: Sequence[int], n: int) -> List[List[int]]:
    inv = inverse_braid_word(secret_word)
    return [list(secret_word) + [i] + inv for i in range(1, n)]


def scramble_braid_word(word: Sequence[int], n: int, rng: random.Random, rounds: int = 900) -> List[int]:
    """
    Rewrite a braid word without changing its braid-group element.

    The SVGs should expose public braid elements, not a visibly factored
    B sigma_i B^-1 spelling. These local moves preserve the element while
    making common conjugator prefixes less visually mechanical.
    """
    w = list(word)
    for _ in range(rounds):
        move = rng.randrange(4)
        if move == 0 and len(w) >= 2:
            j = rng.randrange(len(w) - 1)
            if abs(abs(w[j]) - abs(w[j + 1])) > 1:
                w[j], w[j + 1] = w[j + 1], w[j]
        elif move == 1 and len(w) >= 3:
            j = rng.randrange(len(w) - 2)
            a, b, c = w[j], w[j + 1], w[j + 2]
            if a == c and abs(abs(a) - abs(b)) == 1 and (a > 0) == (b > 0):
                w[j:j + 3] = [b, a, b]
        elif move == 2:
            g = rng.randint(1, n - 1)
            s = g if rng.choice([False, True]) else -g
            j = rng.randrange(len(w) + 1)
            pair = [s, -s] if rng.choice([False, True]) else [-s, s]
            w[j:j] = pair
        else:
            j = 0
            reduced: List[int] = []
            while j < len(w):
                if reduced and reduced[-1] == -w[j] and rng.randrange(3) != 0:
                    reduced.pop()
                else:
                    reduced.append(w[j])
                j += 1
            w = reduced
    return w


def public_picture_words(chal: Challenge) -> Dict[str, List[List[int]]]:
    rng = random.Random((DEFAULT_SEED << 8) ^ chal.n ^ chal.p)
    raw = {
        "bob_public": public_conjugate_words(chal.bob_secret_word, chal.n),
        "alice_ephemeral": public_conjugate_words(chal.alice_secret_word, chal.n),
    }
    return {
        section: [scramble_braid_word(word, chal.n, rng) for word in words]
        for section, words in raw.items()
    }


@dataclass
class Challenge:
    n: int
    p: int
    q0: int
    t0: int
    generators: List[Matrix]
    bob_public: List[Matrix]
    alice_ephemeral: List[Matrix]
    nonce: bytes
    ciphertext: bytes
    tag: bytes
    # These are withheld in a real challenge; retained here for verification.
    bob_secret_word: List[int]
    alice_secret_word: List[int]
    true_shared: Matrix


def make_challenge(
    seed: int = DEFAULT_SEED,
    n: int = DEFAULT_N,
    p: int = DEFAULT_P,
    q0: int = DEFAULT_Q0,
    t0: int = DEFAULT_T0,
    word_length: int = DEFAULT_WORD_LENGTH,
    flag: bytes = DEFAULT_FLAG,
) -> Challenge:
    rng = random.Random(seed)

    gens = lkb_generators(n, p, q0, t0)
    verify_lkb_generators(gens, p)

    # Long random-looking words defeat direct and meet-in-the-middle word search.
    # The intended break remains the linear intertwiner equations.
    b_word = random_braid_word(n, word_length, rng)
    a_word = random_braid_word(n, word_length, rng)
    B = braid_matrix(b_word, gens, p)
    A = braid_matrix(a_word, gens, p)

    bob_public = conjugate_tuple(B, gens, p)
    alice_ephemeral = conjugate_tuple(A, gens, p)
    true_shared = mat_mul(mat_mul(mat_mul(A, B, p), mat_inv(A, p), p), mat_inv(B, p), p)
    key = derive_key(true_shared, p)
    nonce = rng.randbytes(16)
    ciphertext = xor_shake256(key, nonce, flag)
    # lightweight tag so wrong keys fail loudly; not intended as real AEAD
    tag = hashlib.sha256(key + nonce + ciphertext).digest()[:16]

    return Challenge(
        n=n,
        p=p,
        q0=q0,
        t0=t0,
        generators=gens,
        bob_public=bob_public,
        alice_ephemeral=alice_ephemeral,
        nonce=nonce,
        ciphertext=ciphertext,
        tag=tag,
        bob_secret_word=b_word,
        alice_secret_word=a_word,
        true_shared=true_shared,
    )


def challenge_to_quipu_json(
    chal: Challenge,
    cord_manifest: Optional[Dict[str, List[Dict[str, object]]]] = None,
    include_public_matrices: bool = False,
    include_generators: bool = False,
) -> Dict[str, object]:
    p = chal.p
    sections: Dict[str, object] = {
        "ciphertext": {
            "cord": "section",
            "section": "ciphertext",
            "nonce": bytes_to_decimal_cords(chal.nonce),
            "ct": bytes_to_decimal_cords(chal.ciphertext),
            "tag": bytes_to_decimal_cords(chal.tag),
        },
    }
    if cord_manifest is not None:
        sections["cord_pictures"] = {
            "cord": "section",
            "section": "cord_pictures",
            "convention": "Adjacent-crossing diagrams on khipu-style pendant cords; strands are numbered at the primary cord and crossings are read top-to-bottom. A positive crossing has the left/top strand passing over the adjacent right strand; a negative crossing has it passing under.",
            "gallery": "exchange.html",
            "pictures": cord_manifest,
        }
    if include_public_matrices:
        sections["bob_public"] = encode_tuple_as_quipu(chal.bob_public, p, "bob_public", "P")
        sections["alice_ephemeral"] = encode_tuple_as_quipu(chal.alice_ephemeral, p, "alice_ephemeral", "E")
    if include_generators:
        sections["generators"] = encode_tuple_as_quipu(chal.generators, p, "generators", "M")
    return {
        "kind": "Long-Khipu-Braids-v4.0",
        "header": {
            "n": chal.n,
            "p": chal.p,
            "q": chal.q0,
            "t": chal.t0,
            "kdf_context": KDF_CONTEXT.decode(),
            "matrix_key_hint": "recover the shared matrix from the public cord exchange, then serialize entries row-major as fixed-width big-endian integers modulo p",
        },
        "primary_cord": sections,
    }


def challenge_to_public_source(chal: Challenge, cord_manifest: Dict[str, List[Dict[str, object]]]) -> str:
    return f'''#!/usr/bin/env python3
"""
Long Khipu Braids public handout.

The SVG cords in CORD_PICTURES are lossless. Read crossings from the primary
cord downward. Each register contains one adjacent crossing: if the left/top
strand passes over its neighbor, record the positive sign; if it passes under,
record the negative sign. At each crossing, the strand drawn on top is the
over-strand; the other strand continues underneath it. The side knots are just
khipu-style register markers; ignore them when reading the crossings.

The braid parameters are public. The sealed cord opens only after the exchange
has been evaluated into its shared finite-field state.
"""

import hashlib
import operator

KIND = "Long-Khipu-Braids-v4.0"
N = {chal.n}
P = {chal.p}
Q = {chal.q0}
T = {chal.t0}
KDF_CONTEXT = {KDF_CONTEXT!r}
STATE_DIMENSION = N * (N - 1) // 2

CORD_PICTURES = {repr(cord_manifest)}

NONCE = bytes.fromhex("{chal.nonce.hex()}")
CIPHERTEXT = bytes.fromhex("{chal.ciphertext.hex()}")
TAG = bytes.fromhex("{chal.tag.hex()}")


def serialize_state(state):
    width = (P.bit_length() + 7) // 8
    if len(state) != STATE_DIMENSION or any(len(row) != STATE_DIMENSION for row in state):
        raise ValueError("wrong shared-state shape")
    return b"".join((int(x) % P).to_bytes(width, "big") for row in state for x in row)


def derive_key(shared_state):
    return hashlib.sha256(KDF_CONTEXT + serialize_state(shared_state)).digest()


def open_sealed_cord(shared_state):
    key = derive_key(shared_state)
    if hashlib.sha256(key + NONCE + CIPHERTEXT).digest()[:16] != TAG:
        raise ValueError("the cord stays shut")
    stream = hashlib.shake_256(key + NONCE).digest(len(CIPHERTEXT))
    return bytes(operator.xor(a, b) for a, b in zip(CIPHERTEXT, stream))
'''


def public_source_to_quipu_json(path: Path) -> Dict[str, object]:
    ns = runpy.run_path(str(path))
    return {
        "kind": str(ns["KIND"]),
        "header": {
            "n": int(ns["N"]),
            "p": int(ns["P"]),
            "q": int(ns["Q"]),
            "t": int(ns["T"]),
            "kdf_context": bytes(ns["KDF_CONTEXT"]).decode(),
            "matrix_key_hint": "recover the shared matrix from the public cord exchange, then serialize entries row-major as fixed-width big-endian integers modulo p",
        },
        "primary_cord": {
            "ciphertext": {
                "cord": "section",
                "section": "ciphertext",
                "nonce": bytes_to_decimal_cords(bytes(ns["NONCE"])),
                "ct": bytes_to_decimal_cords(bytes(ns["CIPHERTEXT"])),
                "tag": bytes_to_decimal_cords(bytes(ns["TAG"])),
            },
            "cord_pictures": {
                "cord": "section",
                "section": "cord_pictures",
                "convention": "Adjacent-crossing diagrams on khipu-style pendant cords; strands are numbered at the primary cord and crossings are read top-to-bottom. A positive crossing has the left/top strand passing over the adjacent right strand; a negative crossing has it passing under.",
                "gallery": "exchange.html",
                "pictures": ns["CORD_PICTURES"],
            },
        },
    }


def load_public_artifact(path: Path) -> Dict[str, object]:
    if path.suffix == ".py":
        return public_source_to_quipu_json(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def solve_from_quipu_json(doc: Dict[str, object], base_dir: Optional[Path] = None) -> bytes:
    header = doc["header"]
    n = int(header["n"])
    p = int(header["p"])
    q0 = int(header.get("q0", header.get("q")))
    t0 = int(header.get("t0", header.get("t")))
    kdf_context = str(header.get("kdf_context", KDF_CONTEXT.decode())).encode()
    primary = doc["primary_cord"]

    if "generators" in primary:
        Ms = decode_tuple_from_quipu(primary["generators"], p)
    else:
        Ms = lkb_generators(n, p, q0, t0)

    if "bob_public" in primary and "alice_ephemeral" in primary:
        Ps = decode_tuple_from_quipu(primary["bob_public"], p)
        Es = decode_tuple_from_quipu(primary["alice_ephemeral"], p)
    elif "cord_pictures" in primary:
        if base_dir is None:
            raise ValueError("cord picture transcript needs a base directory")
        picture_manifest = primary["cord_pictures"]
        Ps = matrices_from_braid_picture_manifest(picture_manifest, "bob_public", n, Ms, p, base_dir)
        Es = matrices_from_braid_picture_manifest(picture_manifest, "alice_ephemeral", n, Ms, p, base_dir)
    else:
        raise ValueError("public transcript has neither matrix tuples nor cord pictures")
    csec = primary["ciphertext"]
    nonce = decimal_cords_to_bytes(csec["nonce"])
    ciphertext = decimal_cords_to_bytes(csec["ct"])
    tag = decimal_cords_to_bytes(csec["tag"])

    B, nullity_B, rows_B, rank_B = recover_conjugator(Ms, Ps, p)
    A, nullity_A, rows_A, rank_A = recover_conjugator(Ms, Es, p)
    shared = mat_mul(mat_mul(mat_mul(A, B, p), mat_inv(A, p), p), mat_inv(B, p), p)
    key = derive_key(shared, p, kdf_context)
    if hashlib.sha256(key + nonce + ciphertext).digest()[:16] != tag:
        raise ValueError("bad key/tag: exploit did not recover the right shared matrix")
    plaintext = xor_shake256(key, nonce, ciphertext)
    print(f"[solver] B-system: nullity={nullity_B}, rank={rank_B}, rows_processed={rows_B}")
    print(f"[solver] A-system: nullity={nullity_A}, rank={rank_A}, rows_processed={rows_A}")
    return plaintext


# --------------------------- verification helpers ---------------------------

def verify_lkb_generators(gens: Sequence[Matrix], p: int) -> None:
    """Check invertibility and braid relations."""
    for i, G in enumerate(gens, start=1):
        if mat_det(G, p) == 0:
            raise AssertionError(f"LKB generator sigma_{i} is singular")
    m = len(gens)
    # sigma_i sigma_j = sigma_j sigma_i for |i-j| > 1
    for i in range(m):
        for j in range(i + 2, m):
            left = mat_mul(gens[i], gens[j], p)
            right = mat_mul(gens[j], gens[i], p)
            if not mat_eq(left, right, p):
                raise AssertionError(f"far braid relation failed for {i+1},{j+1}")
    # sigma_i sigma_{i+1} sigma_i = sigma_{i+1} sigma_i sigma_{i+1}
    for i in range(m - 1):
        left = mat_mul(mat_mul(gens[i], gens[i + 1], p), gens[i], p)
        right = mat_mul(mat_mul(gens[i + 1], gens[i], p), gens[i + 1], p)
        if not mat_eq(left, right, p):
            raise AssertionError(f"adjacent braid relation failed for {i+1},{i+2}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and solve the Long Khipu Braids v4.0 hard-mode CTF instance.")
    parser.add_argument("--solve-only", metavar="PATH", help="solve an existing quipu JSON instead of generating a new one")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="output public source path when generating")
    parser.add_argument("--json-output", help="author/debug only: also write a machine-readable JSON transcript")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--n", type=int, default=DEFAULT_N)
    parser.add_argument("--p", type=int, default=DEFAULT_P)
    parser.add_argument("--q0", type=int, default=DEFAULT_Q0)
    parser.add_argument("--t0", type=int, default=DEFAULT_T0)
    parser.add_argument("--word-length", type=int, default=DEFAULT_WORD_LENGTH)
    parser.add_argument("--cord-dir", default=DEFAULT_CORD_DIR, help="directory for public crossing-cord SVG artifacts")
    parser.add_argument("--include-public-matrices", action="store_true", help="author/debug only: include public matrix tuples in the JSON")
    parser.add_argument("--include-generators", action="store_true", help="author/debug only: include M_i in the JSON; public hard mode omits them")
    parser.add_argument("--show-secrets", action="store_true", help="author/debug only: print the withheld braid words")
    args = parser.parse_args()

    if args.solve_only:
        doc = load_public_artifact(Path(args.solve_only).resolve())
        recovered = solve_from_quipu_json(doc, Path(args.solve_only).resolve().parent)
        print("[result] plaintext:", recovered.decode())
        return

    chal = make_challenge(
        seed=args.seed,
        n=args.n,
        p=args.p,
        q0=args.q0,
        t0=args.t0,
        word_length=args.word_length,
    )
    print("[setup] n,p,q0,t0 =", chal.n, chal.p, chal.q0, chal.t0)
    print("[setup] d =", len(chal.generators[0]))
    print("[setup] secret word length =", args.word_length)
    if args.show_secrets:
        print("[debug] Bob secret word:", chal.bob_secret_word)
        print("[debug] Alice secret word:", chal.alice_secret_word)

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cord_dir = Path(args.cord_dir).resolve()
    cord_manifest = write_public_cord_pictures(chal, cord_dir, output_path.parent)

    doc = challenge_to_quipu_json(
        chal,
        cord_manifest=cord_manifest,
        include_public_matrices=args.include_public_matrices,
        include_generators=args.include_generators,
    )

    output_path.write_text(challenge_to_public_source(chal, cord_manifest), encoding="utf-8")
    print(f"[setup] wrote {output_path}")
    print(f"[setup] wrote cord pictures under {cord_dir}")
    if args.json_output:
        json_output = Path(args.json_output).resolve()
        with open(json_output, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
        print(f"[setup] wrote debug JSON {json_output}")

    recovered = solve_from_quipu_json(doc, output_path.parent)
    print("[result] plaintext:", recovered.decode())
    assert recovered == DEFAULT_FLAG
    print("[verify] success")


if __name__ == "__main__":
    main()
