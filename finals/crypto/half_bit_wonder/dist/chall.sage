import hashlib
import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
CHALL = ROOT / "chall"

from secret import FLAG, BASE_SEED

q = int(0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141)
L = int(2**20)
T = int(20)
M_PER_BLOCK = int(4096)


def xor_bytes(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


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
        r = rng.randrange(int(1), q)
        while r in used_r:
            r = rng.randrange(int(1), q)
        used_r.add(r)

        y = (r * sk) % q
        ys.append(y)
        samples = []
        nonces = []

        for _ in range(M_PER_BLOCK):
            a = rng.randrange(int(1), L)
            
            k = rng.randrange(int(0), q // 2)
            z = (k - a * y) % q
            samples.append([a, str(z)])
            nonces.append(str(k))

        blocks.append({"r": str(r), "samples": samples})
        all_nonces.append(nonces)

    stream = stream_for_sk(sk, len(FLAG))
    ciphertext = xor_bytes(FLAG, stream)
    public = {
        "name": "Half Bit Wonder",
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


def main():
    DIST.mkdir(parents=True, exist_ok=True)
    CHALL.mkdir(parents=True, exist_ok=True)

    public, private = build_instance(0)

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
