#!/usr/bin/env sage
from operator import xor

import hashlib
import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
CHALL = ROOT / "chall"

NAME = "Half Bit Wonder"
FLAG = b"grey{bLe1cH3nb4Ch3R_iZ_n0_1_Hit_WonD3R_oK4y???}"
BASE_SEED = int(0xB1E1C4EBAEC4E)

# BIP340/secp256k1 scalar field order. This is a realistic Schnorr-sized
# modulus, but the challenge does not publish an elliptic-curve public key.
q = int(0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141)
L = int(2**20)
T = int(20)
M_PER_BLOCK = int(4096)


def xor_bytes(a, b):
    return bytes(xor(x, y) for x, y in zip(a, b))


def stream_for_sk(sk, nbytes):
    label = ("nothing to see here:" + str(sk)).encode()
    return hashlib.shake_256(label).digest(nbytes)


def build_instance(attempt):
    rng = random.Random(int(BASE_SEED + attempt))
    sk = rng.randrange(int(1), q)
    blocks = []
    ys = []
    all_nonces = []
    used_r = set()

    for _ in range(T):
        # Each r_t creates a different public linear view of the same secret.
        # A single reduced-HNP block only localizes y_t to a q/L-sized bin; many
        # independent views can be stitched back together with CVP.
        r = rng.randrange(int(1), q)
        while r in used_r:
            r = rng.randrange(int(1), q)
        used_r.add(r)

        y = (r * sk) % q
        ys.append(y)
        samples = []
        nonces = []

        for _ in range(M_PER_BLOCK):
            # In the full Bleichenbacher/LadderLeak pipeline, side-channel data
            # and collision search produce reduced coefficients. This CTF
            # starts after that stage, so each block samples a_i directly in
            # the reduced range for an independent view y_t = r_t*sk.
            a = rng.randrange(int(1), L)

            # The one-bit leakage modeled here is MSB(k_i)=0. Equivalently,
            # k_i is uniformly chosen from the lower half of Z_q.
            k = rng.randrange(int(0), q // 2)
            z = (k - a * y) % q

            # Large integers are serialized as decimal strings. That keeps the
            # JSON unambiguous across languages whose native number type cannot
            # exactly represent 256-bit integers.
            samples.append([a, str(z)])
            nonces.append(str(k))

        blocks.append({"r": str(r), "samples": samples})
        all_nonces.append(nonces)

    stream = stream_for_sk(sk, len(FLAG))
    ciphertext = xor_bytes(FLAG, stream)
    public = {
        "name": NAME,
        "q": str(q),
        "L": L,
        "T": T,
        "M_per_block": M_PER_BLOCK,
        "blocks": blocks,
        "ciphertext_hex": ciphertext.hex(),
        "kdf_hint": "key = SHAKE256('nothing to see here:' || decimal(sk))",
    }
    private = {
        "flag": FLAG.decode(),
        "sk": str(sk),
        "q": str(q),
        "L": L,
        "T": T,
        "M_per_block": M_PER_BLOCK,
        "ys": [str(y) for y in ys],
        "nonces": all_nonces,
    }
    return public, private


def public_has_accidental_leak(public, private):
    # This is a defensive authoring check, not a cryptographic assumption. It
    # avoids distributing an unlucky JSON instance that literally contains a
    # private decimal/hex string as a substring.
    data = json.dumps(public, sort_keys=True, separators=(",", ":")).encode()
    sk = int(private["sk"])
    probes = [
        FLAG,
        b"grey{",
        str(sk).encode(),
        hex(sk).encode(),
        format(sk, "x").encode(),
    ]
    for y in private["ys"]:
        yi = int(y)
        probes.extend([str(yi).encode(), hex(yi).encode(), format(yi, "x").encode()])
    return any(probe in data for probe in probes)


def main():
    DIST.mkdir(parents=True, exist_ok=True)
    CHALL.mkdir(parents=True, exist_ok=True)

    # Keep generation deterministic while avoiding rare accidental appearances
    # of exact private values in the public JSON. The first non-leaking attempt
    # is stable across regenerations.
    for attempt in range(int(256)):
        public, private = build_instance(attempt)
        if not public_has_accidental_leak(public, private):
            break
    else:
        raise RuntimeError("could not find a non-leaking deterministic instance")

    with (DIST / "output.json").open("w") as f:
        json.dump(public, f, indent=2)
        f.write("\n")

    with (CHALL / "private.json").open("w") as f:
        json.dump(private, f, indent=2)
        f.write("\n")

    print(f"wrote {DIST / 'output.json'}")
    print(f"wrote {CHALL / 'private.json'}")
    print(f"q = {q} ({q.bit_length()} bits)")
    print(f"L = {L}, T = {T}, M_per_block = {M_PER_BLOCK}")
    print(f"total samples = {T * M_PER_BLOCK}, q//L = {q // L}")


if __name__ == "__main__":
    main()
