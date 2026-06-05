# Duality in All Things Solve Writeup

Run from the challenge root:

```bash
python solve/solve.py
python dist/verify.py "$(python solve/solve.py | tail -n1)"
```

The solver uses only `dist/svc_dual_params.pkl` and the public verifier. It does not read `chall/`, metadata, or the original training data.

## Public Artifact

The released object is a pickled dual-form linear SVM artifact. It exposes:

- `support_vectors_`
- `dual_coef_`
- `intercept_`
- `C`

It does not expose the primal `coef_` vector or original training row indices. That omission is the setup for the challenge: the artifact looks stripped down, but the dual representation still contains enough public information to reconstruct the relevant slack behavior.

## Reconstructing The Linear Classifier

For a linear SVM, the primal separating direction is:

```text
w = sum_i alpha_i y_i x_i
```

In scikit-learn's dual representation, `dual_coef_[0]` already stores the signed quantity `alpha_i * y_i`. Therefore the public artifact gives:

```python
w = dual_coef_[0] @ support_vectors_
decision(x) = x @ w + intercept_[0]
```

The sign of each signed dual coefficient gives the support-vector label.

## Finding The Encoded Candidates

Soft-margin SVM dual variables satisfy:

```text
0 <= alpha_i <= C
```

Support vectors with `alpha_i = C` are upper-bound or bounded support vectors. In a soft-margin model, these are the points associated with margin slack:

```text
slack_i = max(0, 1 - y_i * decision(x_i))
```

The challenge encodes the payload in the slack values of the bounded support vectors. The solver therefore:

1. computes `alpha = abs(dual_coef_[0])`;
2. selects `alpha ~= C`;
3. reconstructs `w`;
4. computes labels from `sign(dual_coef_[0])`;
5. computes margins and slack values for those selected support vectors.

The selected slack values split into two bands, representing bits.

## Decoding In Artifact Order

The artifact stores aligned support-vector and dual-coefficient arrays. Applying the bounded-vector mask preserves that public row order, and the challenge construction places the bounded payload candidates in bitstream order. Reordering support vectors and dual coefficients together does not change the classifier, because `dual_coef_[0] @ support_vectors_` is invariant under a shared row permutation.

The bounded slack values visibly split into two one-dimensional bands. Sorting those slack values and thresholding at the largest adjacent gap converts them into bits in the existing artifact order: the lower band is `0`, and the upper band is `1`.

The bitstream format has:

- magic bytes `SVSLACK\0`;
- a 2-byte big-endian flag length;
- UTF-8 flag bytes;
- CRC32 of the flag bytes.

The magic and CRC are not secret shortcuts. They are integrity checks that confirm the public slack decoding and band split are correct.
