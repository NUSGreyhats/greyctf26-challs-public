# Duality in All Things

Local-only CTF challenge package for a sterile machine-learning privacy task.

The participant-facing files are generated into `dist/`. Private generation
inputs and scripts live in `chall/`, and the official solver and inspection aid
live in `solve/`.

## Regenerate

```bash
python chall/generate_challenge.py
```

This reads `chall/flag.txt`, fits a deterministic linear `sklearn.svm.SVC`, and
writes a custom dual-form linear SVM artifact:

- `dist/svc_dual_params.pkl`
- `dist/verify.py`
- `dist/requirements.txt`

`dist/README.md`, `dist/inspect.py`, `dist/info.py`, and `dist/metadata.json`
are intentionally not produced. `solve/inspect.py` and `solve/info.py` are not
kept as author aids.

## Solve Locally

```bash
python solve/solve.py
python dist/verify.py "$(python solve/solve.py | tail -n1)"
```

The intended solve uses complementary slackness:

- signed dual coefficients reveal support-vector labels
- the primal direction is reconstructed from `dual_coef_ @ support_vectors_`
- bounded support vectors identify the relevant candidates
- `intercept_` and the reconstructed primal direction give margins
- slack values form two visible bands that decode to payload bits in artifact row order

## Intended Thought Process

The released object is a dual-form linear SVM artifact. It exposes support
vectors, signed dual coefficients, and an intercept, but it deliberately omits
`coef_` and original training row indices.

The first useful observation is that, for a linear SVM, the primal separating
direction can be reconstructed from the dual:

```text
w = sum_i alpha_i y_i x_i
```

In the artifact, `dual_coef_[0]` already stores the signed quantity
`alpha_i * y_i`, so this becomes:

```python
w = dual_coef_[0] @ support_vectors_
```

The next observation is the soft-margin role of `alpha_i`. Each dual variable
is constrained by:

```text
0 <= alpha_i <= C
```

The value of `alpha_i` describes the point's role:

```text
alpha_i = 0      -> not active in the boundary
0 < alpha_i < C  -> support vector on the margin
alpha_i = C      -> bounded support vector
```

Bounded support vectors are the natural place to inspect if the challenge title
and artifact suggest duality/slack behavior. In a soft-margin SVM, slack
measures margin violation:

```text
xi_i = max(0, 1 - y_i f(x_i))
```

and KKT/complementary-slackness conditions connect that slack behavior to the
upper-bound dual variables. So the solver should filter:

```python
alpha = abs(dual_coef_[0])
bounded = isclose(alpha, C)
```

Then recover labels from the signs:

```python
y = sign(dual_coef_[0])
```

and compute slack using the reconstructed primal direction:

```python
margin = y * (support_vectors_ @ w + intercept_[0])
slack = maximum(0, 1 - margin)
```

At this point, the bounded support vectors have two clear slack bands. Those
bands are the payload bits. The stripped artifact preserves support-vector and
dual-coefficient row alignment, so applying the bounded-vector mask keeps the
intended bitstream order. Reading the slack bands in that artifact row order
gives a bitstream with magic, length, and CRC32.

## Test

```bash
pytest -q
```

Before packaging `dist/`, also check for accidental plaintext leakage:

```bash
grep -R "grey{" dist/ || true
strings dist/svc_dual_params.pkl | grep -i "grey\\|flag\\|svslack" || true
```
