# Solver Writeup

This challenge setup is literally just LadderLeak (https://eprint.iacr.org/2020/615.pdf) but with the side-channel part done for you.

## What HNP Means Here

The Hidden Number Problem is the task of recovering a secret `x` from many
modular expressions that reveal partial information about values of the form:

```text
a_i * x + b_i mod q
```

In signature attacks, the hidden number is usually the signing key or a linear
function of it, and the partial information comes from biased or partially
leaked nonces. Here the challenge skips the side-channel acquisition phase and
directly gives reduced HNP samples.

For each block `t`, the public multiplier `r_t` defines:

```text
y_t = r_t * sk mod q
```

Every sample in that block satisfies:

```text
k_i = z_i + a_i * y_t mod q
0 <= k_i < q/2
```

The nonce condition is the leakage. It says the reconstructed value lands in the
lower half of the modulus. For a wrong guess of `y_t`, the values
`z_i + a_i*y_t mod q` look roughly uniform over `Z_q`. For the correct `y_t`,
they are biased into a half interval.

## Turning Bias Into a Peak

Represent each reconstructed nonce as a point on the unit circle:

```text
exp(2*pi*i*(z_i + a_i*w)/q)
```

If `w = y_t`, all phases come from the lower half of the circle, so their vector
sum has noticeable magnitude. If `w` is wrong, the phases point in mostly
random directions and cancel.

The score is:

```text
Bias(w) = |sum_i exp(2*pi*i*(z_i + a_i*w)/q)|
```

Because the reduced coefficients satisfy `1 <= a_i < L`, evaluate this score on
the grid:

```text
w_j ~= j*q/L
```

Build the length-`L` array:

```text
A[a_i] += exp(2*pi*i*z_i/q)
```

Then:

```python
S = np.fft.ifft(A) * L
```

computes:

```text
sum_a A[a] * exp(+2*pi*i*a*j/L)
```

which approximates `Bias(j*q/L)` for every `j` at once. The largest entries of
`abs(S)` give coarse approximations:

```text
c_t ~= y_t = r_t * sk mod q
```

The solver keeps the top few peaks per block, but the generated instance should
solve from the top peak of every block.

## Why One Block Is Not Enough

The modulus is 256 bits and `L = 2^20`, so one FFT block only identifies a bin
of width about:

```text
q/L ~= 2^236
```

That is intentionally impossible to brute force. The old single-block toy
version used a much smaller `q`, which made this local search feasible but also
made offline brute force of `sk` too plausible.

The fix is to give several independent block views of the same secret:

```text
r_0 * sk ~= c_0 mod q
r_1 * sk ~= c_1 mod q
...
r_{T-1} * sk ~= c_{T-1} mod q
```

Each equation is coarse, but together they identify the same `sk`.

## CVP Recovery

Build the lattice:

```text
Lambda = {
  (r_0*x + q*m_0, ..., r_{T-1}*x + q*m_{T-1})
  : x, m_i in Z
}
```

The target vector is:

```text
c = (c_0, ..., c_{T-1})
```

For the real key `x = sk`, the lattice vector:

```text
(r_0*sk mod q, ..., r_{T-1}*sk mod q)
```

is close to `c`, because each `c_t` came from the correct FFT peak. This is a
bounded-distance/CVP instance in dimension `T = 20`.

The solver uses the row generators:

```text
(r_0, r_1, ..., r_{T-1})
q*e_0
q*e_1
...
q*e_{T-1}
```

Sage's `IntegerLattice(...).approximate_closest_vector` is enough for this
instance. The script also has an `fpylll` exact-CVP fallback. Once a closest
vector `v` is found, recover the key from each coordinate:

```text
sk_t = v_t * r_t^(-1) mod q
```

All recovered `sk_t` values must agree. Finally, derive the SHAKE256 stream
from:

```text
"nothing to see here:" || decimal(sk)
```

Decrypt the ciphertext by XORing that stream with the ciphertext bytes, then
check the flag format.

## Practical Cost

Parameters:

```text
q = secp256k1/BIP340 scalar order
L = 2^20
T = 20
M_per_block = 4096
total samples = 81920
```

The dominant work is `T` FFTs of length `L`, about `20 * 2^20` grid points. The
lattice step is tiny by comparison. On the author machine, the current solver
uses roughly a few hundred MiB of memory and runs in a few seconds.
