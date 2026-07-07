# Half Bit Wonder

It turns out you don't even need a single bit, if you already know how to look
for the bias.

Category: Crypto / HNP / Bleichenbacher / LadderLeak-inspired

This is an offline, serverless challenge about the bias-recovery stage behind
Bleichenbacher-style Hidden Number Problem attacks. The side-channel acquisition
phase is omitted by design: players receive post-processed HNP samples and an
encrypted flag.

The challenge uses the BIP340/secp256k1 scalar order rather than a toy modulus.
To keep exact recovery feasible without a brute-force tail, the public data
contains several independent reduced HNP views of the same secret. For block
`t`, the hidden value is:

```text
y_t = r_t * sk mod q
```

Each block leaks a Fourier-searchable approximation to `y_t`; the final secret
key is recovered by combining those approximations with a small CVP/BDD lattice
step.

The distributed files are:

- `dist/README.md`
- `dist/chall.sage`
- `dist/output.json`

`dist/chall.sage` is included as construction reference only; it imports the
omitted `secret.py` and is not expected to run from the public handout.
`chall/private.json` and `secret.py` are author-only and must not be copied into
`dist/`.

## Regenerate

```sh
make generate
```

## Solve

```sh
make solve
```

## Red-team

```sh
make redteam
```
