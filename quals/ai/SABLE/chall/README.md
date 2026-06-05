# Challenge author notes

This folder contains files used to create and sanity-check the challenge. Do not distribute this folder to players.

## Regenerate distributed artifacts

From the repository root:

```bash
python chall/make_challenge.py
```

This writes:

- `dist/model.pt`
- `dist/public_graph.json`

The real flag is intentionally kept in `chall/flag.txt` and is not copied into `dist`. The deployed checker reads `FLAG` from the environment.

Build the deployment image from the challenge root with:

```bash
docker build -f service/Dockerfile .
```

## Intended vulnerability

The model is a single-target graph attention classifier. It computes:

1. query from `user_target`;
2. keys and values from target neighbors;
3. an SDPA weighted sum over the unordered neighbor set;
4. a spam logit from the target representation and the attended neighbor representation.

The target profile is risky in the base graph because its spammy neighbors receive most of the attention mass. The attacker may add up to six plausible fake friends or followers. If those fake friends have high key compatibility and low value risk, the SDPA softmax gives them enough mass to lower the spam score.

The v2 tuning deliberately puts key compatibility and value risk in tension: high `shared_audience_overlap` and `interaction_strength` steal attention, but those same features also increase the value-side risk contribution. The intended payload balances that tradeoff across six non-identical fake-friend nodes.

## Intended solve

Use `dist/model.pt` and `dist/public_graph.json` to optimize or reason about new-node features. The reference solver in `solve/` uses only `dist` files.

Release checks:

```bash
python chall/make_challenge.py
python chall/audit_package.py
python chall/redteam_suite.py
python solve/solve.py
docker build -f service/Dockerfile .
```

## Defenses against unintended solves

The distributed checker includes these measures:

- no flag in distributed files;
- flag returned only from `os.environ["FLAG"]` on the remote checker;
- strict JSON schema;
- no target/base-node modification interface;
- max 6 new nodes;
- one edge per new node, and only to `user_target`;
- finite numeric feature validation to block NaN/Inf softmax exploits;
- bounded feature ranges to block extreme-vector attacks;
- public plausibility constraints tying strong linkage to supporting risk telemetry;
- pairwise distance checks to reject duplicate fake-friend templates, including templates that differ only in inactive fields;
- strict JSON parsing that rejects duplicate keys and non-standard constants;
- canonical edge ordering and sorted neighbor IDs to remove input-order exploits;
- baseline integrity check requiring the unmodified target to remain high risk;
- author-side red-team suite covering fixed shortcuts, inactive-field jitter, one-linkage ridge payloads, parser abuse, random search, feature-grid search, and model-specific probes;
- no use of `eval`, path loading from payload, pickle upload, or user-controlled model loading.

## Tuning knobs

To adjust difficulty:

- Lower `MAX_NEW_NODES` in `dist/graph_utils.py` and rerun the reference solve.
- Lower or raise `THRESHOLD` in `dist/server.py`.
- Modify the key/value weights in `chall/make_challenge.py`.
- Add more high-risk base neighbors to require better optimization.
