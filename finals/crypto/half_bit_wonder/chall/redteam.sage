#!/usr/bin/env sage
from operator import xor
from sage.all import ZZ, factor, gcd, is_prime

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
CHALL = ROOT / "chall"

EXPECTED_Q = int(0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141)
EXPECTED_PUBLIC_KEYS = {
    "name",
    "q",
    "L",
    "T",
    "M_per_block",
    "blocks",
    "ciphertext_hex",
    "kdf_hint",
}
FORBIDDEN_PUBLIC_KEYS = {
    "flag",
    "secret",
    "sk",
    "y",
    "ys",
    "y_t",
    "nonce",
    "nonces",
    "k",
    "k_values",
    "private",
    "public_key",
    "pubkey",
    "pk",
    "curve",
    "generator",
    "modulus",
    "rsa",
    "signature",
    "signatures",
}


def load_json(path):
    with path.open("r") as f:
        return json.load(f)


def xor_bytes(a, b):
    return bytes(xor(x, y) for x, y in zip(a, b))


def stream_for_sk(sk, nbytes):
    label = ("nothing to see here:" + str(sk)).encode()
    return hashlib.shake_256(label).digest(nbytes)


def assert_public_challenge_source():
    challenge_path = DIST / "chall.sage"
    assert challenge_path.exists(), "missing public construction source"
    assert not (DIST / "crypto.py").exists(), "old public crypto helper should be removed"
    assert not (DIST / "secret.py").exists(), "secret.py copied into dist"
    assert not (DIST / "private.json").exists(), "private.json copied into dist"

    challenge_source = challenge_path.read_text()
    assert "nothing to see here:" in challenge_source

    stale_label = "bleichen" + "bacher:"
    paths_to_scan = [
        CHALL / "gen.sage",
        CHALL / "redteam.sage",
        ROOT / "solve" / "solve.sage",
        challenge_path,
    ]
    for path in paths_to_scan:
        assert stale_label not in path.read_text(), f"stale KDF label found in {path}"
    for path in DIST.rglob("*"):
        if path.is_file():
            assert stale_label.encode() not in path.read_bytes(), f"stale KDF label found in {path}"


def walk_keys(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield str(key)
            yield from walk_keys(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk_keys(value)


def assert_public_schema(public):
    # The public interface is intentionally narrow: reduced HNP blocks plus a
    # ciphertext. Schema-locking prevents accidental publication of a second
    # problem statement such as an EC public key or ECDSA transcript.
    keys = set(public.keys())
    assert keys == EXPECTED_PUBLIC_KEYS, f"unexpected public keys: {sorted(keys)}"
    for key in walk_keys(public):
        assert key.lower() not in FORBIDDEN_PUBLIC_KEYS, f"secret-bearing public field name: {key}"

    assert isinstance(public["blocks"], list)
    for block in public["blocks"]:
        assert set(block.keys()) == {"r", "samples"}
        assert isinstance(block["samples"], list)


def scan_dist_for_leaks(flag, sk, ys, nonces):
    assert not (DIST / "private.json").exists(), "private.json copied into dist"

    # Scan bytes, not parsed JSON, so leaks in README prose or accidental extra
    # files are caught too.
    all_data = b""
    for path in DIST.rglob("*"):
        if path.is_file():
            all_data += path.read_bytes() + b"\n"

    probes = [
        b"grey{",
        flag,
        str(sk).encode(),
        hex(sk).encode(),
        format(sk, "x").encode(),
    ]
    for y in ys:
        probes.extend([str(y).encode(), hex(y).encode(), format(y, "x").encode()])

    for probe in probes:
        assert probe not in all_data, f"leak probe {probe!r} found in dist"

    public_number_tokens = set(re.findall(rb"\d+", all_data))
    nonce_tokens = {str(k).encode() for block_nonces in nonces for k in block_nonces}
    leaked_nonces = public_number_tokens.intersection(nonce_tokens)
    assert not leaked_nonces, "one or more private nonce values appear as public numeric tokens"


def main():
    private_path = CHALL / "private.json"
    public_path = DIST / "output.json"
    assert private_path.exists(), "missing chall/private.json; run make generate"
    assert public_path.exists(), "missing dist/output.json; run make generate"

    private = load_json(private_path)
    public = load_json(public_path)
    assert_public_schema(public)
    assert_public_challenge_source()

    flag = private["flag"].encode()
    sk = int(private["sk"])
    q = int(public["q"])
    L = int(public["L"])
    T = int(public["T"])
    M_per_block = int(public["M_per_block"])
    blocks = public["blocks"]
    ys = [int(y) for y in private["ys"]]
    nonces = [[int(k) for k in block_nonces] for block_nonces in private["nonces"]]

    assert re.fullmatch(rb"grey\{.*\}", flag), "flag format mismatch"
    assert q == EXPECTED_Q
    assert q == int(private["q"])
    assert L == int(private["L"])
    assert T == int(private["T"])
    assert M_per_block == int(private["M_per_block"])
    assert T == int(20)
    assert L == int(2**20)
    assert M_per_block == int(4096)
    assert len(blocks) == T
    assert len(ys) == T
    assert len(nonces) == T

    ciphertext = bytes.fromhex(public["ciphertext_hex"])
    plaintext = xor_bytes(ciphertext, stream_for_sk(sk, len(ciphertext)))
    assert plaintext == flag, "ciphertext does not decrypt under private sk"

    assert is_prime(ZZ(q)), "q is not prime"
    fac = factor(ZZ(q))
    assert len(fac) == 1 and int(fac[0][0]) == q and int(fac[0][1]) == 1, "q has nontrivial factors"
    assert q.bit_length() >= int(250)

    # A single FFT block leaves a huge q/L ambiguity. The challenge must rely
    # on the multi-block CVP combination, not a local brute-force tail.
    assert q // L > 2**230
    assert int(1) <= sk < q

    for t, block in enumerate(blocks):
        r = int(block["r"])
        y = ys[t]
        assert int(1) <= r < q
        assert gcd(ZZ(r), ZZ(q)) == int(1)
        assert y == (r * sk) % q
        assert len(block["samples"]) == M_per_block
        assert len(nonces[t]) == M_per_block

        seen_a = set()
        for i, row in enumerate(block["samples"]):
            assert isinstance(row, list) and len(row) == 2
            a, z = int(row[0]), int(row[1])
            assert int(1) <= a < L
            assert int(0) <= z < q
            k = (z + a * y) % q
            assert int(0) <= k < q // 2
            assert nonces[t][i] == k
            seen_a.add(a)

        assert len(seen_a) * int(100) > int(99) * M_per_block, f"too many repeated a values in block {t}"

    solve_source = (ROOT / "solve" / "solve.sage").read_text()
    # Guard against accidentally reintroducing the old small-q local-search
    # reference solver.
    assert "nearby_offsets" not in solve_source
    assert "RADIUS_FACTOR" not in solve_source
    assert "q // L" not in solve_source or "bit_length" in solve_source

    scan_dist_for_leaks(flag, sk, ys, nonces)

    proc = subprocess.run(
        ["sage", "solve/solve.sage"],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=int(300),
    )
    print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="")
    assert proc.returncode == 0, "public solve script failed"
    assert private["flag"] in proc.stdout, "public solve script did not recover the flag"

    print("redteam checks passed")


if __name__ == "__main__":
    main()
