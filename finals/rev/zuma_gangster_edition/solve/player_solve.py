#!/usr/bin/env python3
"""brute-force solver for the zuma FSOP forge."""
import sys, struct, hashlib
from itertools import product
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as sym_padding

C = "RBGYPO"

# (color, run) -> emitted bytes
MAP = {
    (0,3): b'\x00', (0,4): b'\x10', (1,3): b'\x20', (1,4): b'\x30',
    (2,3): b'\x40', (2,4): b'\x50', (3,3): b'\x08', (3,4): b'\x18',
    (4,3): b'\x28', (4,4): b'\x38', (5,3): b'\x48', (5,4): b'\x58',
    (0,5): b'\x02\xa0', (0,6): b'\x60\xb0', (1,5): b'\x22\xa2', (1,6): b'\x68\xb2',
    (2,5): b'\x42\xa4', (2,6): b'\x70\xb4', (3,5): b'\x0a\x04', (3,6): b'\x78\xb6',
    (4,5): b'\x2a\x34', (4,6): b'\x88\xb8', (5,5): b'\x4a\xe1', (5,6): b'\x98\xba',
    (0,7): b'\x04\xa0\xc0', (0,8): b'\x14\xb0\xc1', (1,7): b'\x24\xa2\x42',
    (1,8): b'\x34\xb2\xc3', (2,7): b'\xe0\xa4\x02', (2,8): b'\xe1\xb4\xc5',
    (3,7): b'\xe2\xa6\x22', (3,8): b'\xe3\xb6\xc7', (4,7): b'\xe4\xa8\xc8',
    (4,8): b'\xe5\xb8\xc9', (5,7): b'\xe6\xaa\xca', (5,8): b'\xe7\xba\xcb',
}

# BODY_SLOT[color][run-3] -> forge write position
SLOT = [
    [16, 19, 10, 17, 13,  8],
    [16, 22, 10, 17,  8, 13],
    [19, 22, 10, 20,  8, 13],
    [22, 23, 12, 17,  8, 13],
    [19, 23, 12, 20,  8, 13],
    [16, 23, 12, 20,  8, 13],
]

# ball chain from binary — scan for achievable clears
CHAIN = [
    3,3,1,4,4,0,5,5,5,1,0,0,0,0,0,4,1,5,5,1,5,5,0,3,2,2,1,2,2,2,2,2,5,0,0,0,0,0,0,4,3,3,3,3,5,2,2,2,2,0,5,1,1,2,1,1,1,1,1,1,5,0,0,2,4,5,5,5,3,0,0,3,1,1,0,4,3,3,3,2,4,4,3,2,1,1,1,1,5,2,2,4,5,5,0,3,0,0,0,1,3,3,1,2,4,4,4,4,5,0,0,
]

# crypto params from fsop.c
SALT = b"no_LLM_to_help_u"
ITERS = 2_000_000
CT = bytes([
    0x6f,0x7d,0x3e,0x9b,0x09,0x30,0x15,0xa7,0xf2,0x61,0x16,0xa0,0x70,0x39,0xd8,0x5c,
    0x76,0x5a,0xe0,0xf5,0x2c,0x61,0x50,0x1f,0x10,0x80,0x99,0x6a,0x9d,0x7a,0xb9,0x30,
    0xb6,0x88,0xcb,0x46,0x19,0x08,0xca,0x76,0xfc,0x6f,0xec,0xc6,0x6d,0xdd,0x56,0x24,
    0xae,0x6f,0x56,0x9b,0xc9,0xd9,0xb0,0x65,0x4e,0xcc,0x09,0x29,0xa5,0x88,0x21,0x3b,
    0x2b,0x31,0xce,0xdf,0x94,0x33,0xdd,0xa1,0x52,0x97,0x37,0xbe,0xc3,0x1c,0xbd,0x7a,
])

REV1 = {v[0]: k for k, v in MAP.items() if len(v) == 1}


def try_decrypt(forge):
    dk = hashlib.pbkdf2_hmac('sha256', forge, SALT, ITERS, dklen=24)
    try:
        dec = Cipher(algorithms.AES(dk), modes.CBC(b'\x00' * 16)).decryptor()
        padded = dec.update(CT) + dec.finalize()
        unpadder = sym_padding.PKCS7(128).unpadder()
        pt = unpadder.update(padded) + unpadder.finalize()
        return pt.decode('ascii')
    except Exception:
        return None


def scan_runs(chain):
    """find all same-color runs -> set of achievable (color, clear_len) pairs."""
    achievable = set()
    i = 0
    while i < len(chain):
        c = chain[i]
        j = i
        while j < len(chain) and chain[j] == c:
            j += 1
        # run of (j-i) balls on chain, +1 shot = clear of (j-i+1)
        achievable.add((c, j - i + 1))
        i = j
    return achievable


def solve(ptr_hex):
    ptr = bytes.fromhex(ptr_hex)
    assert len(ptr) == 8

    ptr_clears = [REV1[b] for b in ptr]

    # chain analysis: which clears can actually happen
    achievable = scan_runs(CHAIN)
    print(f"chain runs: {len(achievable)} achievable clears")
    for c, r in sorted(achievable):
        print(f"  {C[c]}x{r}", end="")
    print("\n")

    # group body clear options by starting forge position
    groups = {}
    for c in range(6):
        for r in range(3, 9):
            pos = SLOT[c][r - 3]
            groups.setdefault(pos, []).append((c, r, MAP[(c, r)]))

    # filter to only chain-achievable clears
    for pos in groups:
        groups[pos] = [(c, r, bs) for c, r, bs in groups[pos] if (c, r) in achievable]

    # effective writer per byte (later position group overwrites earlier)
    eff = {}
    for gpos in sorted(groups):
        if not groups[gpos]:
            continue
        n = len(groups[gpos][0][2])
        for i in range(n):
            eff[gpos + i] = (gpos, i)

    ordered = sorted(p for p in groups if groups[p])
    option_lists = [groups[p] for p in ordered]
    total = 1
    for opts in option_lists:
        total *= len(opts)

    print(f"{len(ordered)} slot groups after chain filter:")
    for p, opts in zip(ordered, option_lists):
        names = ' '.join(f'{C[c]}x{r}' for c, r, _ in opts)
        print(f"  pos {p:2d}: [{names}]")
    print(f"  {total} combos to check\n")

    # brute force, check FSOP constraints
    results = []
    for combo in product(*option_lists):
        forge = bytearray(24)
        forge[:8] = ptr
        for c, r, bs in combo:
            pos = SLOT[c][r - 3]
            for j, b in enumerate(bs):
                forge[pos + j] = b

        cnt = struct.unpack_from('<i', forge, 0x10)[0]
        if cnt < 8:
            continue
        if not (forge[0x14] & 0x40):
            continue
        results.append((bytes(forge), [(c, r) for c, r, _ in combo]))

    unique = set(f for f, _ in results)
    print(f"{len(results)} valid combos -> {len(unique)} unique forge(s)\n")

    # deduplicate and try decryption on each
    seen = set()
    forges = []
    for forge, clears in results:
        if forge not in seen:
            seen.add(forge)
            forges.append((forge, clears))

    print(f"trying PBKDF2 + AES-192-CBC on {len(forges)} forge(s)...\n")
    for forge, clears in forges:
        flag = try_decrypt(forge)
        cnt = struct.unpack_from('<i', forge, 0x10)[0]
        marker = "<<<" if flag else ""
        print(f"forge: {forge.hex()} {marker}")
        print(f"  _cnt={cnt} _flags=0x{forge[0x14]:02x}")
        print(f"  body: {' '.join(f'{C[c]}x{r}' for c,r in clears)}")
        if flag:
            print(f"  FLAG: {flag}")
            return
        print()


if __name__ == '__main__':
    solve(sys.argv[1] if len(sys.argv) > 1 else '0008484028200000')
