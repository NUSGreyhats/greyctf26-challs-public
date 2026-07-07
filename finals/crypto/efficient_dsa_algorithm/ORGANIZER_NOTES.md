# Efficient DSA Algorithm

**Category:** Crypto  
**Difficulty:** Very Easy  
**Concept:** LFSR-generated ECDSA nonces are predictable.

## Player Prompt

The signing service claims to use ECDSA on secp256k1. It also publishes raw
output from its efficient ephemeral-key generator immediately before signing the
important message.

Recover the private signing key and decrypt the flag.

## Player Files

Release only:

- `dist/output.txt`
- `dist/efficient_dsa.sage`
- `dist/secret.py`

`dist/secret.py` is intentionally fake so the public Sage file can show the
construction without leaking the real flag or secrets. If a player runs
`dist/efficient_dsa.sage`, it writes a fake `dist/sample_output.txt`; it must not
overwrite the real `dist/output.txt`.

Do not release:

- `chall/generate.sage`
- `chall/secret.py`
- `solve/`

## Intended Solve

The public Sage file shows a 32-bit binary LFSR. The transcript gives 96 raw
LFSR output bits, then the signing function consumes the next 256 LFSR bits as
the ECDSA nonce `k`.

1. Parse `dist/output.txt`.
2. Run Berlekamp-Massey over GF(2) on `lfsr_output`.
3. Predict the next 256 LFSR bits and interpret them as `k`.
4. Recover the ECDSA private key:

```text
z = SHA256(message) mod n
s = k^-1 * (z + r*d) mod n
d = (s*k - z) * r^-1 mod n
```

5. Decrypt `ciphertext` using `SHA256(d.to_bytes(32, "big"))` repeated as an XOR
   stream.

## Verification

Reference command:

```sh
python3 solve/solve.py
```

Expected output:

```text
grey{LFSR_i5_n0t_4_C5PRNG_at_aL1!!!}
```
