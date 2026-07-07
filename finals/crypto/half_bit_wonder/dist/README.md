# Half Bit Wonder

Bleichenbacher-style attacks on ECDSA can turn tiny nonce leakage into a Hidden
Number Problem. In the full LadderLeak setting, a side channel first gives weak
information about many nonces, and a collision-search/range-reduction phase
turns that information into smaller coefficients.

This challenge starts after that preprocessing. You are given post-processed
samples where the reduced coefficients are already in `[0, L)`.

The public data is split into blocks. For block `t`, a public multiplier `r_t`
defines a hidden block value:

```text
y_t = r_t * sk mod q
```

Every sample in that block satisfies:

```text
k_i = z_i + a_i * y_t mod q
```

The nonce has its most significant bit cleared:

```text
0 <= k_i < q/2
```

The public file contains `q`, `L`, the block count, each block's public `r_t`,
the sample pairs `(a_i, z_i)`, and a ciphertext encrypted under a key derived
from `sk`. There is no server, no live trace collection, and no vulnerable
ECDSA implementation to interact with.

The reduced `a_i` values are the important hint: treat each block like the
output of Bleichenbacher's collision-search stage, look for the modular bias
left by the half-interval condition on `k_i`, and then combine the independent
block views of the same `sk`.

## Encryption

The file `chall.sage` mirrors the reduced-HNP construction and the stream-XOR
encryption. It references an omitted `secret.py`; the distributed public data is
`output.json`, which omits the flag, the secret key, block secrets, nonces, and
private generation seed.

This is not a full ECDSA signer or verifier. It is the post-processed
reduced-HNP layer modeled after the non-side-channel part of the
LadderLeak/Bleichenbacher attack.

The ciphertext is a SHAKE256-derived stream XOR. For the recovered secret key,
written as a decimal integer, compute:

```python
stream = hashlib.shake_256(
    ("nothing to see here:" + decimal_sk).encode()
).digest(message_length)
```

Then decrypt:

```python
message = ciphertext ^ stream
```
