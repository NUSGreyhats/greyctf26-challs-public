from __future__ import annotations

import argparse
import importlib.util
import json
import warnings
from dataclasses import dataclass
from pathlib import Path

import sys

sys.dont_write_bytecode = True

warnings.filterwarnings("ignore", message="Failed to initialize NumPy*", category=UserWarning)
import torch
from z3 import And, If, Int, Or, Solver, sat, unsat


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"


@dataclass(frozen=True)
class Layout:
    prev2_dims: tuple[int, ...]
    prev1_dims: tuple[int, ...]
    sentinel: int


def load_runtime():
    spec = importlib.util.spec_from_file_location("revenge_public_model", DIST_DIR / "model.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load public model.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RevengeModel.from_paths(DIST_DIR / "model.pt", DIST_DIR / "alphabet.json")


class MechanisticSolver:
    def __init__(self) -> None:
        info = json.loads((DIST_DIR / "alphabet.json").read_text(encoding="utf-8"))
        self.alphabet = info["alphabet"]
        self.n = int(info["payload_length"])
        self.a = len(self.alphabet)
        self.model = load_runtime()
        self.binary_dim = self.model.binary_dim
        self.packed_dim = self.model.packed_dim
        self.memory_dim = self.model.memory_dim
        self.layout = self.recover_layout()

    def decode(self, step: int, cell: torch.Tensor) -> torch.Tensor:
        # The public model stores the recurrent state behind a per-step
        # orthogonal transport. Unpacking cancels that transport and exposes
        # the stable binary/memory chart used by the generated verifier.
        return self.model._cu[step] @ cell.to(dtype=torch.float64)

    def encode(self, step: int, packed: torch.Tensor) -> torch.Tensor:
        # Re-apply the public transport so patched packed states can be fed
        # back through the real one-step transition function.
        return self.model._cw[step] @ packed.to(dtype=torch.float64)

    def cells_for_indices(self, xs: torch.Tensor) -> torch.Tensor:
        cell = self.model.state.initial.detach().clone().to(dtype=torch.float64)
        cells = [cell.detach().clone()]
        for step, raw_idx in enumerate(xs.to(dtype=torch.int64).tolist()):
            cell = self.model._advance(step, cell, int(raw_idx))
            cells.append(cell.detach().clone())
        return torch.stack(cells)

    def recover_layout(self) -> Layout:
        # Use a known probe string only to label activation behavior, not to
        # learn the flag. Prev1 and prev2 bits are shifted one-hot copies of
        # earlier probe symbols; the loop index itself supplies phase.
        probe = (self.alphabet * ((self.n // self.a) + 2))[: self.n]
        xs = torch.tensor([self.alphabet.index(ch) for ch in probe], dtype=torch.int64)
        cells = self.cells_for_indices(xs)
        packed = torch.stack([self.decode(step, cells[step]) for step in range(self.n + 1)])
        active = packed[:, : self.binary_dim] > 0.0

        used: set[int] = set()

        def recover_shifted_register(delay: int) -> tuple[int, ...]:
            dims: list[int] = []
            for value in range(self.a + 1):
                if value == self.a:
                    expected = [step for step in range(self.n + 1) if step < delay]
                else:
                    expected = [
                        step
                        for step in range(self.n + 1)
                        if step >= delay and self.alphabet.index(probe[step - delay]) == value
                    ]
                candidates = [
                    dim
                    for dim in range(self.binary_dim)
                    if dim not in used
                    and dim not in dims
                    and active[:, dim].nonzero().flatten().tolist() == expected
                ]
                if not candidates:
                    raise RuntimeError("failed to recover previous-character register from public traces")
                dims.append(min(candidates))
            used.update(dims)
            return tuple(dims)

        prev2_dims = recover_shifted_register(delay=2)
        prev1_dims = recover_shifted_register(delay=1)
        return Layout(
            prev2_dims=prev2_dims,
            prev1_dims=prev1_dims,
            sentinel=self.a,
        )

    def patched_packed(self, step: int, prev2: int, prev1: int) -> torch.Tensor:
        # Build an artificial recurrent context for a single transition. This
        # lets us ask "if the automaton were at this phase with these previous
        # characters, would reading ch preserve this terminal feature?"
        x = torch.ones((self.packed_dim,), dtype=torch.float64)
        x[: self.binary_dim] = 1.0
        x[list(self.layout.prev2_dims)] = -1.0
        x[self.layout.prev2_dims[prev2]] = 1.0
        x[list(self.layout.prev1_dims)] = -1.0
        x[self.layout.prev1_dims[prev1]] = 1.0
        x[self.binary_dim :] = 0.0
        return x

    def transition_value(self, dim: int, step: int, prev2: int, prev1: int, ch: int) -> bool:
        cell = self.encode(step, self.patched_packed(step, prev2, prev1))
        nxt = self.model._advance(step, cell, ch)
        packed_next = self.decode(step + 1, nxt)
        return bool(packed_next[dim].item() > 0.0)

    def causal_binary_dims(self) -> list[int]:
        # Terminal acceptance is mediated by evidence bits. Flip each packed
        # binary feature in isolation and keep only features that can change a
        # scoring evidence row.
        probe_w = self.model.classifier.features.weight.to(dtype=torch.float64)
        probe_b = self.model.classifier.features.bias.to(dtype=torch.float64)
        head = self.model.classifier.output.weight[0].to(dtype=torch.float64)
        selected = [idx for idx, value in enumerate(head.tolist()) if value > 0.5]
        base = torch.ones((self.packed_dim,), dtype=torch.float64)
        base[self.binary_dim :] = 0.0
        causal: list[int] = []
        for dim in range(self.binary_dim):
            lo = base.clone()
            hi = base.clone()
            lo[dim] = -1.0
            hi[dim] = 1.0
            e_lo = torch.where(
                probe_w[:, self.model.readout_dim :] @ lo + probe_b >= 0.0,
                torch.ones((self.model.evidence_dim,), dtype=torch.float64),
                -torch.ones((self.model.evidence_dim,), dtype=torch.float64),
            )
            e_hi = torch.where(
                probe_w[:, self.model.readout_dim :] @ hi + probe_b >= 0.0,
                torch.ones((self.model.evidence_dim,), dtype=torch.float64),
                -torch.ones((self.model.evidence_dim,), dtype=torch.float64),
            )
            if any(e_lo[idx].item() != e_hi[idx].item() for idx in selected):
                causal.append(dim)
        excluded = set(self.layout.prev2_dims)
        excluded.update(self.layout.prev1_dims)
        return [dim for dim in causal if dim not in excluded]

    def relation_for_dim(self, dim: int) -> tuple[list[int], list[list[tuple[int, int]]]]:
        # Convert one causal terminal feature into a regular-language view:
        # allowed first characters plus allowed adjacent transitions.
        start = [
            ch
            for ch in range(self.a)
            if self.transition_value(dim, 0, self.layout.sentinel, self.layout.sentinel, ch)
        ]
        pairs: list[list[tuple[int, int]]] = []
        for step in range(1, self.n):
            allowed: list[tuple[int, int]] = []
            prev2 = self.layout.sentinel if step == 1 else 0
            for prev1 in range(self.a):
                for ch in range(self.a):
                    if self.transition_value(dim, step, prev2, prev1, ch):
                        allowed.append((prev1, ch))
            pairs.append(allowed)
        return start, pairs

    def memory_targets(self) -> dict[int, int]:
        feature_w = self.model.classifier.features.weight.to(dtype=torch.float64)
        feature_b = self.model.classifier.features.bias.to(dtype=torch.float64)
        head = self.model.classifier.output.weight[0].to(dtype=torch.float64)
        selected = [idx for idx, value in enumerate(head.tolist()) if value > 0.5]
        bounds: dict[int, list[float]] = {idx: [] for idx in range(self.memory_dim)}
        for row in selected:
            coeffs = feature_w[row, self.model.readout_dim + self.binary_dim : self.model.readout_dim + self.binary_dim + self.memory_dim]
            mem_idx = int(torch.argmax(coeffs.abs()).item())
            coeff = float(coeffs[mem_idx].item())
            if abs(coeff) < 0.5:
                continue
            bounds[mem_idx].append(float((-feature_b[row] / coeff).item()))
        targets: dict[int, int] = {}
        for mem_idx, values in bounds.items():
            if len(values) >= 2:
                targets[mem_idx] = int(round(sum(values) / len(values)))
        return targets

    def z3_candidate(
        self,
        start: list[int],
        pairs: list[list[tuple[int, int]]],
        memory_targets: dict[int, int] | None = None,
    ) -> tuple[str | None, bool]:
        # Z3 is used as a compact uniqueness proof for the recovered relation:
        # find one path, then assert that every position differs somewhere and
        # check that no second path exists.
        if not start or any(not step_pairs for step_pairs in pairs):
            return None, False
        xs = [Int(f"x_{idx}") for idx in range(self.n)]
        solver = Solver()
        for x in xs:
            solver.add(And(x >= 0, x < self.a))
        solver.add(Or([xs[0] == value for value in start]))
        for step, step_pairs in enumerate(pairs, start=1):
            solver.add(Or([And(xs[step - 1] == prev, xs[step] == ch) for prev, ch in step_pairs]))
        if memory_targets:
            increments = (self.model.core.value.weight.detach().to(dtype=torch.float64) * 128.0).round().to(dtype=torch.int64)
            for mem_idx, target in memory_targets.items():
                terms = []
                for step in range(self.n):
                    terms.append(sum(If(xs[step] == ch, int(increments[step, ch, mem_idx].item()), 0) for ch in range(self.a)))
                solver.add(sum(terms) == target)
        if solver.check() != sat:
            return None, False
        model = solver.model()
        values = [int(model[x].as_long()) for x in xs]
        payload = "".join(self.alphabet[value] for value in values)
        solver.add(Or([xs[idx] != values[idx] for idx in range(self.n)]))
        return payload, solver.check() == unsat

    def solve(self) -> tuple[str, dict[str, object]]:
        causal = self.causal_binary_dims()
        reports: list[str] = []
        relations: list[tuple[int, list[int], list[list[tuple[int, int]]], int]] = []
        for dim in causal:
            start, pairs = self.relation_for_dim(dim)
            edge_count = sum(len(row) for row in pairs) + len(start)
            if not start or any(not row for row in pairs):
                reports.append(f"dim {dim}: relation unsat")
                continue
            relations.append((dim, start, pairs, edge_count))
            reports.append(f"dim {dim}: recovered relation ({edge_count} edges)")

        memory_targets = self.memory_targets()

        def attempt(chosen: list[tuple[int, list[int], list[list[tuple[int, int]]], int]]) -> tuple[str | None, bool, int]:
            if not chosen:
                return None, False, 0
            start_set = set(chosen[0][1])
            pair_sets = [set(row) for row in chosen[0][2]]
            for _, start, pairs, _ in chosen[1:]:
                start_set &= set(start)
                for idx, row in enumerate(pairs):
                    pair_sets[idx] &= set(row)
            start = sorted(start_set)
            pairs = [sorted(row) for row in pair_sets]
            candidate, unique = self.z3_candidate(start, pairs, memory_targets)
            return candidate, unique, len(start) + sum(len(row) for row in pairs)

        attempts = [relations]
        attempts.extend([relations[:idx] + relations[idx + 1 :] for idx in range(len(relations))])
        for chosen in attempts:
            candidate, unique, edge_count = attempt(chosen)
            if candidate is None:
                reports.append(f"combined {len(chosen)} relations: unsat")
                continue
            accepted = self.model.run_payload(candidate)["accepted"]
            reports.append(f"combined {len(chosen)} relations: candidate={candidate!r} unique={unique} accepted={accepted}")
            if unique and accepted:
                return candidate, {
                    "causal_dims": causal,
                    "chosen_dim": [dim for dim, _, _, _ in chosen],
                    "relation_edges": edge_count,
                    "memory_targets": memory_targets,
                    "attempts": reports,
                    "unique": unique,
                }
        raise RuntimeError("failed to recover an accepting unique payload")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Solve jurgens_revenge from the public bundle.")
    parser.add_argument("--report", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    solver = MechanisticSolver()
    payload, info = solver.solve()
    flag = f"grey{{{payload}}}"
    print(flag)
    if args.report:
        print()
        print("Recovered mechanism:")
        print("- activation chart: inverted public cell transport matrices")
        print("- register recovery: inferred previous-character registers from public traces")
        print("- causal patching: identified terminal binary parents from output evidence")
        print("- relation recovery: patched recurrent state and measured one-step feature survival")
        print("- solver backend: Z3 over recovered transition relations")
        print(f"- causal binary parents tested: {len(info['causal_dims'])}")
        print(f"- selected causal features: {info['chosen_dim']}")
        print(f"- recovered combined transition edges: {info['relation_edges']}")
        print(f"- recovered terminal memory targets: {info['memory_targets']}")
        print("- decoy circuits: rejected by terminal acceptance check")
        print("- Z3 uniqueness: proved")


if __name__ == "__main__":
    main()
