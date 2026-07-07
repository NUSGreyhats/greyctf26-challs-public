# Solver Writeup

The challenge omits the Lawrence-Krammer-Bigelow generator matrices, but it
does publish enough parameters to reconstruct them:

```text
n, p, q, t, basis v_{j,k}
```

After reconstructing the matrices `M_i`, solve the linear intertwiner systems:

```text
B M_i = P_i B
A M_i = E_i A
```

The non-zero scalar ambiguity in `A` and `B` cancels in the commutator:

```text
K = A B A^-1 B^-1
```

Derive the SHA256 key from `K`, verify the tag, and decrypt the SHAKE256 stream
cipher. The reference Sage solver is `solve.sage`.
