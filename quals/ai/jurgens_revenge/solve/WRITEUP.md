# jurgens_revenge solve writeup

The checker only prints `accepted` or `rejected`, but the public bundle is not a pure black box. It ships a compact recurrent model, its normal-looking `state_dict`, and the public runtime needed to evaluate it locally.

## Setup

From the challenge root:

```bash
python -m pip install -r dist/requirements.txt
python -m pip install -r solve/requirements.txt
python solve/solve.py --report
```

The solver prints the recovered `grey{...}` flag and a short mechanism report.

## Public surface

The solver uses only:

- `dist/model.pt`
- `dist/model.py`
- `dist/alphabet.json`

It does not import `chall/`, read `chall/metadata.json`, or use private generator tables. The challenge-specific knowledge comes from inspecting public tensors and instrumenting public recurrent execution.

## Method

The public object looks like a conventional recurrent classifier: an embedding layer, a recurrent core, a linear readout, and a classifier head. Internally, the recurrent state is transported through a generated cell basis. The solver inverts that transport to obtain a stable packed chart where many coordinates behave like hard binary features and the final coordinates behave like additive memory accumulators.

First, the solver runs a known probe string through the public model. This is not a guess at the flag; it labels activation behavior. Coordinates that match one-symbol and two-symbol shifted copies of the probe identify previous-character registers. The loop index supplies phase, so there is no explicit phase register in the public recurrent state.

With those registers recovered, the solver constructs artificial packed states for a single step. For each step and previous-character context, it encodes the packed state back into a cell, feeds one candidate character through the real transition function, and unpacks the next cell. This gives direct access to one-step transition behavior without relying on the private generator.

Next, the solver finds terminal causal features. It flips each binary packed feature at the terminal state and recomputes the public classifier evidence. Any feature that can change a scoring evidence row is a candidate parent of acceptance. Previous-character bookkeeping features are excluded, leaving status-like verifier features and decoys.

For each strong causal feature, the solver recovers a relation:

- allowed first characters;
- allowed adjacent `(previous, current)` transitions for each later position.

No single accepted relation is intended to be enough. The solver intersects the recovered relations, recovers the terminal memory targets from the classifier evidence rows, and adds the corresponding additive-memory equations. Z3 then finds a satisfying 55-character path and proves uniqueness by asking for a second path that differs in at least one position. The candidate is finally checked with the public model, so structured decoy circuits that do not accept are rejected.

## Expected result

`python solve/solve.py --report` should end with:

```text
Z3 uniqueness: proved
```

and print the accepted flag before the report.
