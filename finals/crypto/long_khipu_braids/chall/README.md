# Long Khipu Braids Author Notes

Generate player artifacts with:

```sh
python3 chall/generate_challenge.py
```

Run this from the `long_khipu_braids` directory. The generator writes
`dist/challenge.py`, `dist/exchange.html`, and `dist/cords/*.svg`, then
immediately solves the public picture transcript as a sanity check. The public
hard-mode instance intentionally omits the raw public matrices and LKB generator
matrices; pass `--json-output` together with `--include-public-matrices` or
`--include-generators` only for author debugging.

The flag is stored in `generate_challenge.py` as `DEFAULT_FLAG`.
