# Author Notes

This challenge is not a real ECDSA implementation. It isolates the Hidden
Number Problem core that appears after side-channel observations have already
been converted into algebraic samples.

The modulus is the BIP340/secp256k1 scalar order. For each block `t`,
generation chooses a public random multiplier `r_t` and defines:

```text
y_t = r_t * sk mod q
```

For each sample in that block, generation chooses a reduced coefficient `a_i`
and a biased nonce `k_i` such that:

```text
k_i = z_i + a_i * y_t mod q
0 <= k_i < q/2
```

The values `a_i` are generated directly in `[1, L)`. This models the output of
Bleichenbacher's collision-search/range-reduction stage from the full attack.
The CTF intentionally skips the side-channel and collision-search work so the
player focuses on the reduced HNP recovery stage.

The ciphertext is encrypted with a stream derived from `sk`, so players cannot
simply recognize the key from public metadata. They must recover `sk` accurately
enough to decrypt the flag.

The expected solve path is:

1. Build one bias-polynomial/DFT array per block from `(a_i, z_i)`.
2. Use FFT-style searches to recover approximations `y_t ~= c_t`.
3. Combine `r_t * sk ~= c_t mod q` with a low-dimensional CVP/BDD lattice.
4. Decrypt with the recovered `sk` and check the flag format.

Unintended factorization and discrete-log shortcuts are intentionally absent:
`q` is a public prime, there is no RSA modulus, no public group generator, no
public key, and no ECDSA signature transcript. The large modulus also removes
the old toy-size exhaustive search path.
