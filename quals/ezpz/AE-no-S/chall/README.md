# AE-no-S Author Notes

`generate.py` creates the participant files in `dist/`:

- `challenge.py`: public s-boxless AES implementation
- `README.md`: participant-facing summary
- `output.txt`: known plaintext/ciphertext pairs and encrypted padded flag

The local flag is defined only in `chall/generate.py`. The participant output gives `E(0)`, all 128 one-bit basis encryptions, and the encrypted padded flag.

The generator executes the exact same `CHALLENGE_SOURCE` string that it writes to `dist/challenge.py`. This keeps the generated transcript tied to the participant implementation without importing from `dist/`.

## Red Team Notes

Checks performed before finalization:

- Flag leakage: `dist/` was searched for `flag{`; the real flag is not present in participant files.
- Key leakage: `dist/output.txt` contains only plaintext/ciphertext pairs and the encrypted flag. The secret and generated schedule are not written to `dist/`, and no deterministic seed is published.
- Import boundary: `chall/generate.py` does not import from `dist/`; `dist/challenge.py` imports from neither `chall` nor `solve`; `solve/solve.py` imports only from `dist.challenge`.
- Trivial solve paths: `dist/challenge.py` has no decrypt function, no flag plaintext, no secret, no generated schedule dump, and no script to regenerate the secret.
- Challenge solvability: `solve/solve.py` reconstructs the affine map from `dist/output.txt` and recovers the flag without using `chall/`.
- Matrix invertibility: generation reconstructs the public basis matrix and fails loudly unless it has rank 128.
- Consistency: generation uses the same source that is written to `dist/challenge.py`.
- Dependency sanity: `chall/generate.py` and `dist/` use only the Python 3 standard library. The official solver requires SageMath so it can use native matrices over GF(2).

Recommended local checks:

```sh
pyenv activate cs5242
python3 chall/generate.py
grep -R "flag{" dist/ || true
grep -R "urandom\|seed\|round_key\|FLAG\|key =" dist/ || true
sage -python solve/solve.py
```
