#!/usr/bin/env python3
from ast import literal_eval
from hashlib import sha256
from itertools import cycle
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def parse_output(path=ROOT / "dist" / "output.txt"):
    # The transcript is written as simple Python literals, so literal_eval
    # safely recovers ints, bytes, and strings without importing chall code.
    rows = (line.partition("=") for line in Path(path).read_text().splitlines())
    return {key.strip(): literal_eval(value.strip()) for key, sep, value in rows if sep}


def berlekamp_massey(bits):
    # c is the current connection polynomial; b is the last polynomial that
    # caused a length increase; L is the current recurrence length; m is the
    # distance since that last update.
    c, b, L, m = [1], [1], 0, 1
    for n, bit in enumerate(bits):
        # Discrepancy: compare the observed bit with what the current
        # recurrence predicts from the previous L bits.
        d = bit
        for i in range(1, min(L + 1, len(c))):
            d ^= c[i] & bits[n - i]
        if d == 0:
            m += 1
            continue
        # A discrepancy means the current recurrence is wrong at position n.
        # Shift the previous update polynomial by m and XOR it into c.
        old = c[:]
        c += [0] * max(0, len(b) + m - len(c))
        for i, coeff in enumerate(b):
            c[i + m] ^= coeff
        # If the old recurrence was too short to explain the prefix, increase
        # its length and remember the old polynomial for future corrections.
        if 2 * L <= n:
            L, b, m = n + 1 - L, old, 1
        else:
            m += 1
    return c[: L + 1]


def predict(bits, recurrence, count):
    bits = bits[:]
    for _ in range(count):
        # The recurrence coefficients say which previous bits XOR together to
        # form the next LFSR output bit.
        bits.append(sum(recurrence[i] & bits[-i] for i in range(1, len(recurrence))) & 1)
    return bits[-count:]


def main():
    out = parse_output()
    bits = [int(bit) for bit in out["lfsr_output"]]
    # The next 256 predicted LFSR bits are consumed by efficient_dsa.sign as k.
    k = int("".join(map(str, predict(bits, berlekamp_massey(bits), 256))), 2) % out["n"]
    z = int.from_bytes(sha256(out["message"]).digest(), "big") % out["n"]
    # From s = k^-1 * (z + r*d), recover d = (s*k - z) / r mod n.
    d = ((out["s"] * k - z) * pow(out["r"], -1, out["n"])) % out["n"]
    key = sha256(d.to_bytes(32, "big")).digest()
    # The flag is encrypted with SHA256(d) repeated as an XOR stream.
    print(bytes(a ^ b for a, b in zip(bytes.fromhex(out["ciphertext"]), cycle(key))).decode())


if __name__ == "__main__":
    main()
