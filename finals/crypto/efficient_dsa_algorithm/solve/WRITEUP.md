# Efficient DSA Algorithm Solve Writeup

Run from the challenge root:

```bash
python solve/solve.py
```

The solver uses only:

- `dist/output.txt`
- `dist/efficient_dsa.sage` as public context

It does not read `chall/secret.py` or the private generator.

## Public Setup

The public transcript contains curve parameters, the signed message, 96 raw LFSR output bits, the ECDSA public key, one signature `(r, s)`, and the encrypted flag. The public `efficient_dsa.sage` is a redacted copy of the generator using a fake `secret.py`; it shows that the nonce generator is a binary LFSR and that `sign()` consumes 256 LFSR bits to build the ECDSA nonce `k`.

The important detail is timing: `output.txt` gives LFSR output immediately before the signing call. The next 256 bits produced by the same LFSR are the nonce bits.

## Vulnerability

ECDSA requires a secret unpredictable nonce. Here the nonce comes from a linear recurrence over GF(2). A short enough prefix of raw LFSR output lets Berlekamp-Massey recover the shortest recurrence that matches the stream.

Once the recurrence is known, future bits are predictable. That gives the signing nonce `k`.

## Recovering The Nonce

The solve script:

1. parses `output.txt` as Python literals;
2. converts the public `lfsr_output` string into bits;
3. runs Berlekamp-Massey over GF(2);
4. extends the bitstream by 256 bits;
5. interprets those predicted bits as the nonce integer `k`.

Berlekamp-Massey maintains a current connection polynomial and updates it whenever the current bit disagrees with the recurrence prediction. The returned coefficients define how to compute every next bit from previous bits.

## Recovering The Private Key

ECDSA signing computes:

```text
z = SHA256(message) mod n
s = k^-1 * (z + r*d) mod n
```

Rearranging for the private key gives:

```text
d = (s*k - z) * r^-1 mod n
```

All values on the right are public once `k` has been predicted.

## Decrypting The Flag

The generator encrypts the flag with a repeating XOR key derived from the private key:

```text
key = SHA256(d.to_bytes(32, "big"))
```

After recovering `d`, the solver derives the same key and XORs it with `ciphertext` to recover the flag.
