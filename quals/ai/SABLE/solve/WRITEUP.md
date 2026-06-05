# SABLE Solve Writeup

The solver intentionally reads only from `../dist`. It does not read the real flag, `chall/`, or any author-only metadata. The local checker returns a dummy flag unless the deployed service sets `FLAG`, so the proof of success is the checker returning `ok: true` with risk below the public threshold.

Run from the challenge root:

```bash
python solve/solve.py
python dist/server.py solve/payload.json --debug
```

## Public Setup

The useful public files are:

- `dist/server.py`: JSON input path/stdin handling, success threshold, and output format.
- `dist/graph_utils.py`: feature names, allowed ranges, payload schema, node/edge rules, and plausibility checks.
- `dist/model.py`: the SDPA graph-attention model.
- `dist/model.pt`: trained model weights.
- `dist/public_graph.json`: the base graph containing `user_target` and its neighbors.

The payload schema is recoverable directly from `server.py` and `graph_utils.py`. A submission is a JSON object with `new_nodes` and `new_edges`. Each submitted node has an ID and exactly the eight public features listed in `FEATURE_NAMES`. Each new edge must connect that submitted node to `user_target`.

## Vulnerability

This is part of a family of attacks on distributed systems known as Sybil attacks. Put simply, it is astroturfing the target system with fake accounts that look like good friends. Only that the attack here is on a Graph Neural Network rather than some other recommendation system. Hence the name sounds like "Sybil" (idk, Codex made the name "SABLE").

The model classifies the target by attending from the target feature vector over the target's neighbor feature vectors. In `model.py`, the target becomes a query, neighbors become keys and values, and PyTorch SDPA computes a weighted average of neighbor values.

The base graph has risky neighbors that make the target look high-risk. The attacker can add up to six plausible new neighbors. If those new neighbors have high key compatibility but low enough value-side risk, the attention softmax assigns them most of the attention mass. That dilutes the original risky neighbors and drops the final spam logit below the threshold.

## Solver Strategy

The solver performs differentiable optimization over six submitted feature vectors:

1. Read the public model and base graph.
2. Convert unconstrained optimizer variables into legal feature ranges with a sigmoid and the public `FEATURE_BOUNDS`.
3. Append the candidate fake-friend features to the base neighbor tensor.
4. Minimize the model logit, because lower logit means lower spam risk after sigmoid.
5. Add differentiable penalties matching the public plausibility and diversity checks.
6. Repair the best optimizer output into a stable, valid JSON payload.
7. Re-run the public checker with `--debug` to prove the payload is accepted.

The optimizer uses several deterministic restarts. Restarts avoid depending on one unlucky random initialization, while the final payload is still validated by `dist/graph_utils.py` and `dist/server.py`.

## Constraint Handling

The public validator is not fully differentiable because it rejects JSON objects with hard errors. The solver mirrors those hard checks with soft penalties during optimization:

- linkage/risk floor penalties for `report_rate`, `external_link_rate`, `shared_audience_overlap`, and `interaction_strength`;
- a penalty for "too clean" high-realness/high-trust profiles with strong linkage;
- all-feature and active-feature pairwise L1 distance penalties to avoid near duplicates;
- small imbalanced-linkage penalties to avoid invalid edge cases.

After gradient optimization, `repair_friends` deliberately snaps the active linkage fields onto a known valid ridge and raises risk-floor features if needed. It also sets `post_rate_norm` and `profile_age_norm` to distinct values so JSON rounding cannot accidentally create duplicate-looking profiles.

## Why The Output Is A Real Solve

`solve.py` regenerates `solve/payload.json` from public files each time. It does not depend on the existing `payload.json` contents. The generated payload is passed through the same public validation and server code challengers receive. The final debug output shows the fake-friend nodes receiving most attention mass and the risk falling below the threshold.
