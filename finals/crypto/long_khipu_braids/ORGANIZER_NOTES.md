# Author Notes: Long Khipu Braids

This version ships public braid pictures instead of public LKB matrices.

Participants should reconstruct Artin braid words from the SVG cords, identify
that the `n,p,q,t` parameters fit the Lawrence-Krammer-Bigelow representation,
then run the same intertwiner attack:

```text
P_i = B M_i B^-1  =>  B M_i = P_i B
E_i = A M_i A^-1  =>  A M_i = E_i A
```

Each equation is linear in the unknown entries of `A` or `B`. Recover the
conjugators up to scalar, compute:

```text
K = A B A^-1 B^-1
```

The scalar ambiguity cancels.

Current default parameters:

```text
n = 8
p = 10000019
q = 17
t = 42
secret word length = 96
```

The public source handout intentionally contains only:

```text
ciphertext constants
CORD_PICTURES
```

It does not contain `bob_public`, `alice_ephemeral`, or `generators`. If an
author wants a machine-readable debug transcript, run with `--json-output` and
optionally `--include-public-matrices` or `--include-generators`.

The SVGs are lossless under the documented convention: strands are numbered at
the primary cord, crossings are read top-to-bottom, and each register contains
one adjacent crossing. The generator verifies this by parsing the SVG geometry,
evaluating the decoded braid words in LKB, and solving the resulting public
instance.

Verified commands:

```bash
python3 chall/generate_challenge.py
python3 chall/generate_challenge.py --solve-only dist/challenge.py
sage solve/solve.sage dist/challenge.py
```
