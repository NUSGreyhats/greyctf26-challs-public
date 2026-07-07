#!/usr/bin/env sage
from hashlib import sha256
from importlib import util
from itertools import cycle
from pathlib import Path

from sage.all import EllipticCurve, GF, ZZ, inverse_mod


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
DIST_DIR = ROOT / "dist"

secret_spec = util.spec_from_file_location("secret", SCRIPT_DIR / "secret.py")
secret = util.module_from_spec(secret_spec)
secret_spec.loader.exec_module(secret)


P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
GX = 55066263022277343669578718895168534326250603453777594175500187360389116729240
GY = 32670510020758816978083085130507043184471273380659243275938904335757337482424

E = EllipticCurve(GF(P), [0, 7])
G = E(GX, GY)


def point_mul(k, point=G):
    result = ZZ(k) * point
    if result == E(0):
        return None
    x, y = result.xy()
    return int(x), int(y)


class LFSR:
    def __init__(self, state, mask, width=32):
        state = int(state)
        mask = int(mask)
        width = int(width)
        one = int(1)
        self.state = state & ((one << width) - one)
        self.mask = mask & ((one << width) - one)
        self.width = width

    def bit(self):
        one = int(1)
        out = self.state & one
        feedback = (self.state & self.mask).bit_count() & one
        self.state = (self.state >> one) | (feedback << (self.width - one))
        return out

    def bits(self, count):
        return [self.bit() for _ in range(count)]


def lfsr_int(lfsr, count):
    return int("".join(map(str, lfsr.bits(count))), 2)


def sign(message, private_key, lfsr):
    z = int.from_bytes(sha256(message).digest(), "big") % N
    k = lfsr_int(lfsr, 256) % N
    if k == 0:
        raise RuntimeError("zero nonce")
    r = point_mul(k)[0] % N
    s = inverse_mod(k, N) * (z + r * private_key) % N
    return int(r), int(s)


def main():
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    flag = secret.FLAG
    private_key = ZZ(secret.SECRET_D) % N
    lfsr = LFSR(secret.SECRET_LFSR_STATE, secret.SECRET_LFSR_MASK)
    lfsr_output = "".join(map(str, lfsr.bits(96)))

    message = b"give me the flag"
    r, s = sign(message, private_key, lfsr)
    pub = point_mul(private_key)
    key = sha256(int(private_key).to_bytes(int(32), "big")).digest()
    ciphertext = bytes(a ^^ b for a, b in zip(flag, cycle(key))).hex()

    (DIST_DIR / "sample_output.txt").write_text(
        "\n".join(
            [
                f"p = {hex(P)}",
                f"n = {hex(N)}",
                f"Gx = {hex(GX)}",
                f"Gy = {hex(GY)}",
                f"message = {message!r}",
                f"lfsr_output = {lfsr_output!r}",
                f"public_key_x = {hex(pub[0])}",
                f"public_key_y = {hex(pub[1])}",
                f"r = {hex(r)}",
                f"s = {hex(s)}",
                f"ciphertext = {ciphertext!r}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
