#!/usr/bin/env python3
"""Reference solve for the SDPA graph-attention fake-friend challenge.

Important isolation rule: this solver reads only files from ../dist. It does not read author-only files, and it does not know the real flag.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

import torch

HERE = Path(__file__).resolve().parent
DIST = (HERE / ".." / "dist").resolve()
sys.path.insert(0, str(DIST))

from graph_utils import (  # noqa: E402
    ACTIVE_DIVERSITY_FEATURES,
    FEATURE_BOUNDS,
    FEATURE_NAMES,
    MIN_ACTIVE_PAIRWISE_L1,
    MIN_PAIRWISE_L1,
    TARGET_ID,
    PayloadError,
    load_json,
    target_ego_tensors,
    validate_and_apply_payload,
)
from model import load_model  # noqa: E402

MODEL_PATH = DIST / "model.pt"
GRAPH_PATH = DIST / "public_graph.json"
SERVER_PATH = DIST / "server.py"
OUT_PAYLOAD = HERE / "payload.json"
N_FRIENDS = 6


def bounded_features(raw: torch.Tensor) -> torch.Tensor:
    """Map unconstrained optimizer variables into the server's feature bounds."""
    # Optimize in unconstrained space, then squash with sigmoid so every step
    # stays inside the public per-feature bounds.
    vals = torch.sigmoid(raw)
    lows = torch.tensor([FEATURE_BOUNDS[name][0] for name in FEATURE_NAMES], dtype=torch.float32)
    highs = torch.tensor([FEATURE_BOUNDS[name][1] for name in FEATURE_NAMES], dtype=torch.float32)
    return lows + vals * (highs - lows)


def inverse_sigmoid(x: torch.Tensor) -> torch.Tensor:
    # Used to seed Adam near a hand-picked feasible region while still letting
    # the optimizer operate in unconstrained coordinates.
    x = x.clamp(1e-4, 1 - 1e-4)
    return torch.log(x / (1 - x))


def constraint_penalty(friends: torch.Tensor) -> torch.Tensor:
    # These soft penalties mirror the hard public validation rules. They guide
    # gradient descent toward valid payloads instead of waiting until the final
    # JSON validation step to reject bad candidates.
    reports = friends[:, FEATURE_NAMES.index("report_rate")]
    external_link = friends[:, FEATURE_NAMES.index("external_link_rate")]
    realness = friends[:, FEATURE_NAMES.index("profile_realness")]
    audience_overlap = friends[:, FEATURE_NAMES.index("shared_audience_overlap")]
    interactions = friends[:, FEATURE_NAMES.index("interaction_strength")]
    trust_score = friends[:, FEATURE_NAMES.index("trust_score")]

    penalty = friends.new_tensor(0.0)
    # Strong linkage requires supporting risk telemetry.
    penalty = penalty + torch.relu((audience_overlap - 0.70) * 0.36 - reports).pow(2).sum()
    penalty = penalty + torch.relu((interactions - 0.70) * 0.36 - external_link).pow(2).sum()
    penalty = penalty + torch.relu((audience_overlap + interactions - 1.30) * 0.24 - reports - external_link).pow(2).sum()

    too_clean = (
        torch.relu(0.09 - reports - external_link)
        * torch.relu(realness + trust_score - 1.84)
        * torch.relu(audience_overlap + interactions - 1.50)
    )
    penalty = penalty + too_clean.pow(2).sum()

    # Encourage all submitted nodes, and their active spam/attention features,
    # to stay separated enough to pass pairwise L1 diversity checks.
    for i in range(friends.shape[0]):
        for j in range(i + 1, friends.shape[0]):
            distance = torch.sum(torch.abs(friends[i] - friends[j]))
            penalty = penalty + torch.relu(MIN_PAIRWISE_L1 + 0.006 - distance).pow(2)
            active_distance = torch.sum(
                torch.abs(friends[i, [FEATURE_NAMES.index(name) for name in ACTIVE_DIVERSITY_FEATURES]]
                - friends[j, [FEATURE_NAMES.index(name) for name in ACTIVE_DIVERSITY_FEATURES]])
            )
            penalty = penalty + torch.relu(MIN_ACTIVE_PAIRWISE_L1 + 0.004 - active_distance).pow(2)

    penalty = penalty + torch.relu(audience_overlap - interactions - 0.235).pow(2).sum()
    # Extra smoothing near a known fragile validation edge: high shared_audience_overlap
    # with too-low interaction_strength tends to get rejected.
    penalty = penalty + (torch.relu(audience_overlap - 0.90) * torch.relu(0.724 - interactions)).pow(2).sum()

    return penalty


def repair_friends(friends: torch.Tensor) -> torch.Tensor:
    """Project nearly valid optimizer output into the public validation rules."""
    repaired = friends.clone()
    idx = {name: FEATURE_NAMES.index(name) for name in FEATURE_NAMES}

    # Give every fake friend a distinct active telemetry profile. The chosen ridge is
    # still the SDPA weakness: strong enough target linkage to steal attention,
    # but with the required risk floors and high realness/trust to keep values low.
    shared_values = torch.tensor([0.88, 0.90, 0.92, 0.94, 0.96, 0.98], dtype=repaired.dtype)
    relation_values = torch.tensor([0.84, 0.82, 0.80, 0.78, 0.76, 0.74], dtype=repaired.dtype)
    repaired[:, idx["shared_audience_overlap"]] = shared_values[: repaired.shape[0]]
    repaired[:, idx["interaction_strength"]] = relation_values[: repaired.shape[0]]
    repaired[:, idx["profile_realness"]] = torch.clamp(repaired[:, idx["profile_realness"]], min=0.995)
    repaired[:, idx["trust_score"]] = torch.clamp(repaired[:, idx["trust_score"]], min=0.995)

    for i in range(repaired.shape[0]):
        shared = repaired[i, idx["shared_audience_overlap"]].item()
        relation = repaired[i, idx["interaction_strength"]].item()
        report_floor = max(0.0, shared - 0.70) * 0.36 + 0.010
        external_link_floor = max(0.0, relation - 0.70) * 0.36 + 0.010
        repaired[i, idx["report_rate"]] = max(repaired[i, idx["report_rate"]].item(), report_floor)
        repaired[i, idx["external_link_rate"]] = max(repaired[i, idx["external_link_rate"]].item(), external_link_floor)

        combined_floor = max(0.0, shared + relation - 1.30) * 0.24 + 0.010
        combined = repaired[i, idx["report_rate"]] + repaired[i, idx["external_link_rate"]]
        if combined.item() < combined_floor:
            gap = (combined_floor - combined.item()) / 2.0
            repaired[i, idx["report_rate"]] += gap
            repaired[i, idx["external_link_rate"]] += gap

    # post_rate_norm and profile_age_norm do not drive the model. Use them to make the six
    # submitted profiles clearly non-identical after JSON rounding.
    tx_values = torch.linspace(0.16, 0.46, repaired.shape[0])
    age_values = torch.linspace(0.40, 0.16, repaired.shape[0])
    repaired[:, idx["post_rate_norm"]] = tx_values
    repaired[:, idx["profile_age_norm"]] = age_values
    return repaired


def initial_raw(restart: int) -> torch.Tensor:
    lows = torch.tensor([FEATURE_BOUNDS[name][0] for name in FEATURE_NAMES], dtype=torch.float32)
    highs = torch.tensor([FEATURE_BOUNDS[name][1] for name in FEATURE_NAMES], dtype=torch.float32)
    base = torch.tensor([0.28, 0.25, 0.10, 0.10, 0.93, 0.88, 0.88, 0.94], dtype=torch.float32)
    # Each restart begins near a plausible ridge but with small noise and a
    # ladder across rows so Adam explores distinct fake-friend profiles.
    noise = torch.randn(N_FRIENDS, len(FEATURE_NAMES)) * 0.025
    ladder = torch.linspace(-0.045, 0.045, N_FRIENDS).unsqueeze(1)
    direction = torch.tensor([1.0, -0.4, 0.3, -0.3, -0.5, 0.5, -0.5, 0.4])
    target = (base + noise + ladder * direction).clamp(lows + 1e-3, highs - 1e-3)
    normalized = (target - lows) / (highs - lows)
    torch.manual_seed(2026 + restart)
    return inverse_sigmoid(normalized).detach().requires_grad_(True)


def optimize_friend_set() -> torch.Tensor:
    model = load_model(MODEL_PATH)
    graph = load_json(GRAPH_PATH)
    target_x, base_neighbor_x, _ = target_ego_tensors(graph, TARGET_ID)

    best = None
    torch.manual_seed(2026)
    for restart in range(10):
        raw = initial_raw(restart)
        opt = torch.optim.Adam([raw], lr=0.055)
        for step in range(700):
            opt.zero_grad()
            friends = bounded_features(raw)
            neighbor_x = torch.cat([base_neighbor_x, friends], dim=0)
            logit = model(target_x, neighbor_x)
            penalty = constraint_penalty(friends)
            # Minimize spam logit while softly rewarding benign-looking profile_realness
            # and trust_score. The large penalty keeps validity more important
            # than marginal model-score gains.
            benign_bonus = friends[:, FEATURE_NAMES.index("profile_realness")].mean() + friends[:, FEATURE_NAMES.index("trust_score")].mean()
            loss = logit + 600.0 * penalty - 0.012 * benign_bonus
            loss.backward()
            opt.step()
            if step in {420, 560}:
                for group in opt.param_groups:
                    group["lr"] *= 0.45

        with torch.no_grad():
            # Convert nearly valid continuous output into the exact JSON ridge
            # used by the final payload, then test it through public validation.
            friends = repair_friends(bounded_features(raw).detach())
            payload = build_payload(friends)
            try:
                candidate_graph = validate_and_apply_payload(graph, payload)
            except PayloadError:
                continue
            candidate_x, candidate_neighbors, _ = target_ego_tensors(candidate_graph, TARGET_ID)
            risk = torch.sigmoid(model(candidate_x, candidate_neighbors)).item()
            if best is None or risk < best[0]:
                best = (risk, friends)

    if best is None:
        raise RuntimeError("failed to find a valid fake-friend set")
    return best[1]


def build_payload(friends: torch.Tensor) -> dict:
    nodes = []
    edges = []
    for i in range(N_FRIENDS):
        node_id = f"friend_{i:02d}"
        values = [float(x) for x in friends[i].tolist()]
        features = {name: round(values[j], 6) for j, name in enumerate(FEATURE_NAMES)}
        nodes.append({"id": node_id, "features": features})
        edges.append([TARGET_ID, node_id])
    return {"new_nodes": nodes, "new_edges": edges}


def main() -> int:
    friends = optimize_friend_set()
    payload = build_payload(friends)
    OUT_PAYLOAD.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT_PAYLOAD}")
    print("optimized fake-friend feature vectors:")
    for node in payload["new_nodes"]:
        summary = ", ".join(f"{name}={node['features'][name]:.4f}" for name in FEATURE_NAMES)
        print(f"  {node['id']}: {summary}")

    result = subprocess.run(
        # The final step is not a private oracle: it invokes the participant
        # checker from dist/ against the payload that was just regenerated.
        [sys.executable, str(SERVER_PATH), str(OUT_PAYLOAD), "--debug"],
        cwd=str(DIST),
        text=True,
        capture_output=True,
        check=False,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
