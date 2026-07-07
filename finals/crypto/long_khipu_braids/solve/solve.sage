# SageMath reference solver for Long Khipu Braids v4.0 hard-mode challenges.
# Run with: sage solve.sage ../dist/challenge.py
#
# The challenge intentionally omits the generator matrices M_i. This solver
# reconstructs the Lawrence-Krammer-Bigelow generator action over GF(p), then
# solves X M_i = P_i X for the hidden conjugators.

import sys, json, hashlib, random, operator, os, re, runpy
import xml.etree.ElementTree as ET
from sage.all import *

KDF_CONTEXT = b"Long-Khipu-Braids-v4.0"


def lkb_basis(n):
    return [(j, k) for j in range(1, n + 1) for k in range(j + 1, n + 1)]


def lkb_generators(n, p, q0, t0, F):
    """
    Bigelow/Sage-compatible Lawrence-Krammer-Bigelow generator matrices.

    Basis is v_{j,k}, 1 <= j < k <= n, lexicographic order.
    Matrix columns are images of basis vectors.
    """
    q = F(q0)
    t = F(t0)
    q2_minus_q = q*q - q
    basis = lkb_basis(n)
    idx = {pair: a for a, pair in enumerate(basis)}
    d = len(basis)
    gens = []

    def add(coeffs, pair, coeff):
        assert pair[0] < pair[1], pair
        coeffs[pair] = coeffs.get(pair, F(0)) + F(coeff)

    for i in range(1, n):
        M = Matrix(F, d, d, 0)
        for col, (j, k) in enumerate(basis):
            coeffs = {}
            if i == j and i == k - 1:
                add(coeffs, (j, k), -t*q*q)
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
                # Sage-compatible convention: (1-q) q t
                add(coeffs, (i, k), (1 - q) * q * t)
            elif i == k:
                add(coeffs, (j, k + 1), 1)
            else:
                raise RuntimeError(f"unhandled case i={i}, j={j}, k={k}")
            for pair, coeff in coeffs.items():
                M[idx[pair], col] = coeff
        gens.append(M)
    verify_lkb_generators(gens)
    return gens


def verify_lkb_generators(gens):
    for g in gens:
        assert g.det() != 0
    for i in range(len(gens)):
        for j in range(i + 2, len(gens)):
            assert gens[i] * gens[j] == gens[j] * gens[i]
    for i in range(len(gens) - 1):
            assert gens[i] * gens[i+1] * gens[i] == gens[i+1] * gens[i] * gens[i+1]


def braid_matrix(word, gens):
    M = identity_matrix(gens[0].base_ring(), gens[0].nrows())
    inv_cache = {}
    for s in word:
        idx = abs(s) - 1
        G = gens[idx]
        if s < 0:
            if idx not in inv_cache:
                inv_cache[idx] = G.inverse()
            G = inv_cache[idx]
        M *= G
    return M


def integer_from_digits_fixed(digits_units_first):
    return sum(Integer(d) * (10 ** i) for i, d in enumerate(digits_units_first))


def decode_field_element_from_knots(obj, p):
    digits = [int(reg["turns"]) for reg in obj["registers_low_to_high"]]
    x = int(integer_from_digits_fixed(digits))
    if not (0 <= x < p):
        raise ValueError(f"decoded field element {x} not in GF({p})")
    return x


def decode_matrix_from_quipu(obj, p, F):
    rows = []
    for row in obj["rows"]:
        rows.append([F(decode_field_element_from_knots(entry, p)) for entry in row["entries"]])
    return Matrix(F, rows)


def decode_tuple_from_quipu(obj, p, F):
    return [decode_matrix_from_quipu(mobj, p, F) for mobj in obj["matrices"]]


def decimal_cords_to_bytes(cords):
    out = []
    for c in cords:
        x = int(integer_from_digits_fixed([int(reg["turns"]) for reg in c["registers_low_to_high"]]))
        if not (0 <= x <= 255):
            raise ValueError(f"bad byte value: {x}")
        out.append(x)
    return bytes(out)


def _svg_path_endpoints(d):
    nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", d)]
    if len(nums) < 8:
        raise ValueError(f"cannot parse SVG path: {d!r}")
    return nums[0], nums[1], nums[-2], nums[-1]


def read_braid_svg_word(path, n):
    root = ET.parse(path).getroot()
    lane_gap = 42.0
    margin_x = 62.0
    word = []
    for elem in root.iter():
        if "crossing" not in elem.attrib.get("class", "").split():
            continue
        paths = [child for child in list(elem) if child.tag.endswith("path")]
        if len(paths) != 2:
            raise ValueError(f"unexpected crossing shape in {path}")
        # The generator writes the under-stand first and the over-strand second,
        # so the second path determined the crossing sign.
        x0, y0, x1, _ = _svg_path_endpoints(paths[1].attrib["d"])
        lane = round((min(x0, x1) - margin_x) / lane_gap)
        if not (0 <= lane < n - 1):
            raise ValueError(f"decoded bad crossing lane {lane + 1} in {path}")
        sign = 1 if x0 < x1 else -1
        word.append((y0, sign * (lane + 1)))
    return [s for _, s in sorted(word)]


def matrices_from_braid_picture_manifest(manifest, section, n, gens, base_dir):
    section = {"bob_public": "bob", "alice_ephemeral": "alice"}.get(section, section)
    mats = []
    for picture in manifest["pictures"][section]:
        path = os.path.join(base_dir, picture["file"])
        word = read_braid_svg_word(path, n)
        if "crossings" in picture and len(word) != int(picture["crossings"]):
            raise ValueError(f"crossing count mismatch for {path}")
        mats.append(braid_matrix(word, gens))
    return mats


def public_source_to_doc(path):
    ns = runpy.run_path(path)
    return {
        "kind": str(ns["KIND"]),
        "header": {
            "n": int(ns["N"]),
            "p": int(ns["P"]),
            "q": int(ns["Q"]),
            "t": int(ns["T"]),
            "kdf_context": bytes(ns["KDF_CONTEXT"]).decode(),
        },
        "primary_cord": {
            "ciphertext": {
                "nonce": [{"registers_low_to_high": [{"turns": d} for d in reversed(str(b).zfill(3))]} for b in bytes(ns["NONCE"])],
                "ct": [{"registers_low_to_high": [{"turns": d} for d in reversed(str(b).zfill(3))]} for b in bytes(ns["CIPHERTEXT"])],
                "tag": [{"registers_low_to_high": [{"turns": d} for d in reversed(str(b).zfill(3))]} for b in bytes(ns["TAG"])],
            },
            "cord_pictures": {
                "pictures": ns["CORD_PICTURES"],
            },
        },
    }


def load_public_artifact(path):
    if path.endswith(".py"):
        return public_source_to_doc(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def matrix_to_bytes(M, p):
    width = (int(p).bit_length() + 7) // 8
    return b"".join(int(x).to_bytes(width, "big") for row in M.rows() for x in row)


def derive_key(Kmat, p, context=KDF_CONTEXT):
    return hashlib.sha256(context + matrix_to_bytes(Kmat, p)).digest()


def xor_shake256(key, nonce, data):
    stream = hashlib.shake_256(key + nonce).digest(len(data))
    return bytes(operator.xor(a, b) for a, b in zip(data, stream))


def recover_conjugator(Ms, Ps, F):
    d = Ms[0].nrows()
    rows = []
    for M, P in zip(Ms, Ps):
        for r in range(d):
            for c in range(d):
                eq = [F(0)] * (d * d)
                for k in range(d):
                    # Unknowns are row-major: x_{0,0}, x_{0,1}, ...
                    eq[r * d + k] += M[k, c]
                    eq[k * d + c] -= P[r, k]
                rows.append(eq)
    Big = Matrix(F, rows)
    ker = Big.right_kernel()
    for v in ker.basis():
        X = Matrix(F, d, d, list(v))
        if X.det() != 0:
            assert all(X * M == P * X for M, P in zip(Ms, Ps))
            return X, ker.dimension()
    # In unusual parameter sets the nullspace may be larger. Try random linear combinations.
    basis = list(ker.basis())
    rng = random.Random(1337)
    for _ in range(300):
        coeffs = [F(rng.randrange(int(F.order()))) for _ in basis]
        if all(c == 0 for c in coeffs):
            continue
        v = sum((c * b for c, b in zip(coeffs, basis)), vector(F, [0] * (d * d)))
        X = Matrix(F, d, d, list(v))
        if X.det() != 0:
            assert all(X * M == P * X for M, P in zip(Ms, Ps))
            return X, ker.dimension()
    raise ValueError(f"no invertible conjugator found; nullity={ker.dimension()}")


def solve(path):
    doc = load_public_artifact(path)
    h = doc["header"]
    n = int(h["n"])
    p = int(h["p"])
    q0 = int(h.get("q0", h.get("q")))
    t0 = int(h.get("t0", h.get("t")))
    global KDF_CONTEXT
    if "kdf_context" in h:
        KDF_CONTEXT = h["kdf_context"].encode()
    F = GF(p)
    primary = doc["primary_cord"]

    if "generators" in primary:
        Ms = decode_tuple_from_quipu(primary["generators"], p, F)
    else:
        Ms = lkb_generators(n, p, q0, t0, F)

    if "bob_public" in primary and "alice_ephemeral" in primary:
        Ps = decode_tuple_from_quipu(primary["bob_public"], p, F)
        Es = decode_tuple_from_quipu(primary["alice_ephemeral"], p, F)
    elif "cord_pictures" in primary:
        base_dir = os.path.dirname(os.path.abspath(path))
        picture_manifest = primary["cord_pictures"]
        Ps = matrices_from_braid_picture_manifest(picture_manifest, "bob_public", n, Ms, base_dir)
        Es = matrices_from_braid_picture_manifest(picture_manifest, "alice_ephemeral", n, Ms, base_dir)
    else:
        raise ValueError("public transcript has neither matrix tuples nor cord pictures")
    csec = primary["ciphertext"]
    nonce = decimal_cords_to_bytes(csec["nonce"])
    ciphertext = decimal_cords_to_bytes(csec["ct"])
    tag = decimal_cords_to_bytes(csec["tag"])

    B, nb = recover_conjugator(Ms, Ps, F)
    A, na = recover_conjugator(Ms, Es, F)
    shared = A * B * A.inverse() * B.inverse()
    key = derive_key(shared, p, KDF_CONTEXT)
    if hashlib.sha256(key + nonce + ciphertext).digest()[:16] != tag:
        raise ValueError("bad key/tag")
    print(f"nullities: B={nb}, A={na}")
    print(xor_shake256(key, nonce, ciphertext).decode())


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: sage solve.sage ../dist/challenge.py")
        sys.exit(2)
    solve(sys.argv[1])
