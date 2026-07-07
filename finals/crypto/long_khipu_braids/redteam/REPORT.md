# Long Khipu Braids Redteam Notes

Scope: bounded search for easier-than-intended solves against
`dist/challenge.py` and the public SVG braid cords.

## Checked

- Public artifact leakage:
  - `dist/challenge.py` has only `CORD_PICTURES` and ciphertext constants.
  - No literal flag, default seed, secret braid words, true shared matrix,
    `bob_public`, `alice_ephemeral`, or `generators` section appears in `dist/`.
- Braid picture losslessness:
  - The generated SVGs decode to one Artin braid word per public cord under the
    documented top-to-bottom convention.
  - Decoded words evaluate to the intended public conjugates before solving.
- Symmetric layer shortcuts:
  - Known flag prefix gives only SHAKE256 keystream bytes, with no practical key
    inversion path.
  - The 16-byte nonce exposes 128 bits of MT19937 output at most, far short of a
    full Python `random` state recovery.
- Direct public algebra:
  - After decoding the SVGs and reconstructing the matrix representation, the
    public-to-public intertwiner `Y` satisfying `Y P_i = E_i Y` is uniquely
    recoverable up to scalar, but `Y`, `Y^-1`, `[Y,P_i]`, and `[Y,E_i]` do not
    pass the ciphertext tag.
- Invariants:
  - Determinants are conjugacy-invariant as expected, so
    `det(M_i) == det(P_i) == det(E_i)`.
  - This exposes only abelianized/conjugacy-invariant data, not the serialized
    matrix commutator used in the KDF.
- Small-order checks:
  - No public/generator matrix had order <= 64.

## Tool Output

```text
[artifact] public generators leaked: False
[artifact] public matrices leaked: False
[artifact] public sections: ciphertext, cord_pictures
[params] n,p,q,t,d: 8 10000019 17 42 28
[cipher] lengths nonce/ct/tag: 16 77 16
[rng] nonce exposes 128 bits; MT19937 state recovery needs 624 32-bit outputs
[direct-intertwiner] P->E nullity/rank/rows: 1 783 783
[candidate-keys] simple/direct candidates passing tag: none
[invariants] det(M_i)==det(P_i)==det(E_i): True
[invariants] first generator determinant: 8744159
[invariants] gcd(28, p-1): 14
[orders] public/generator matrix orders <=64: none
[summary] no checked shortcut recovered the flag
```

## Residual Risk

If `chall/generate_challenge.py` is accidentally distributed to players, the
flag and default seed are literal source constants. That is normal for this repo
layout but means the release process must publish only `dist/` artifacts.

The intended solve now has an extra recognition step: decode the public braid
pictures, choose the LKB representation, and solve the intertwiner systems. I
did not find a simpler public-data shortcut.
