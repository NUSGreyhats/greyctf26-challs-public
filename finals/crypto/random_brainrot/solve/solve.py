from pwn import *
import collections
import random
import math

HOST = "localhost"
PORT = 34067

LEN = 16
SAMPLES = 100


class PRNG:
    def __init__(self, r, x):
        self.r = r
        self.x = x

        for _ in range(1000):
            self.step()

    def step(self):
        self.x = self.r * self.x * (1 - self.x)

    def generate(self):
        while True:
            self.step()
            yield int(self.x * 256)


def build_model(r, trials=5000):
    cnt = collections.Counter()

    for _ in range(trials):
        p = PRNG(r, random.random())

        for b in encrypt_zero(p):
            cnt[b] += 1

    total = sum(cnt.values())

    for i in range(256):
        if cnt[i] == 0:
            cnt[i] = 1

    M = {}
    for i in range(256):
        M[i] = -math.log(cnt[i] / total)

    return M


def encrypt_zero(p):
    g = p.generate()
    return [next(g) for _ in range(LEN)]


while True:
    r = remote(HOST, PORT)

    RR = float(r.recvline().decode().strip())
    log.info(f"RR = {RR}")

    log.info("building distribution model...")
    M = build_model(RR)

    samples = [[] for _ in range(LEN)]

    for _ in range(SAMPLES):
        r.sendlineafter(b":", ("00" * LEN).encode())

        line = r.recvline().decode().strip()

        ct = bytes.fromhex(
            line
        )

        for i, b in enumerate(ct):
            samples[i].append(b)

    secret = bytearray(LEN)

    for pos in range(LEN):

        best_score = float("inf")
        best_key = 0

        for guess in range(256):

            score = 0.0

            for c in samples[pos]:
                score += M[c ^ guess]

            if score < best_score:
                best_score = score
                best_key = guess

        secret[pos] = best_key

    log.success(f"secret = {secret.hex()}")

    r.sendlineafter(b":", secret.hex().encode())


    if b"stop" in r.readline():
        print(r.readline())
        break

    r.close()
