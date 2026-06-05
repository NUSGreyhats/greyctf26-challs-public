#!/usr/bin/env python3
"""Build the distributed artifacts for the SDPA graph attention challenge.

Run from repository root or from chall/. This script writes only into ../dist.
The flag is intentionally not copied into dist; the deployed checker reads FLAG
from the environment.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

import torch

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
sys.path.insert(0, str(DIST))

from model import SDPAEgoSpamNet  # noqa: E402


def feature(post_rate_norm, profile_age_norm, report_rate, external_link_rate, profile_realness, shared_audience_overlap, interaction_strength, trust_score):
    return {
        "post_rate_norm": post_rate_norm,
        "profile_age_norm": profile_age_norm,
        "report_rate": report_rate,
        "external_link_rate": external_link_rate,
        "profile_realness": profile_realness,
        "shared_audience_overlap": shared_audience_overlap,
        "interaction_strength": interaction_strength,
        "trust_score": trust_score,
    }


def build_graph():
    nodes = {
        "user_target": {
            "role": "target_profile",
            "features": feature(0.48, 0.72, 0.23, 0.18, 0.70, 0.00, 0.00, 0.50),
        },
        "user_giveaway_ring_01": {
            "role": "giveaway_spam_neighbor",
            "features": feature(0.92, 0.08, 0.94, 0.86, 0.02, 1.00, 1.00, 0.04),
        },
        "user_giveaway_ring_02": {
            "role": "giveaway_spam_neighbor",
            "features": feature(0.84, 0.14, 0.88, 0.80, 0.06, 0.96, 0.93, 0.10),
        },
        "user_linkfarm_17": {
            "role": "link_farm_neighbor",
            "features": feature(0.76, 0.19, 0.74, 0.64, 0.12, 0.85, 0.90, 0.14),
        },
        "user_creator_21": {
            "role": "ordinary_neighbor",
            "features": feature(0.34, 0.83, 0.05, 0.02, 0.92, 0.12, 0.26, 0.86),
        },
        "user_mod_09": {
            "role": "ordinary_neighbor",
            "features": feature(0.18, 0.91, 0.02, 0.01, 0.98, 0.05, 0.18, 0.94),
        },
        "user_lurker_44": {
            "role": "ordinary_neighbor",
            "features": feature(0.05, 0.66, 0.01, 0.00, 0.75, 0.02, 0.08, 0.70),
        },
    }
    edges = [
        ["user_target", "user_giveaway_ring_01"],
        ["user_target", "user_giveaway_ring_02"],
        ["user_target", "user_linkfarm_17"],
        ["user_target", "user_creator_21"],
        ["user_target", "user_mod_09"],
        ["user_target", "user_lurker_44"],
        # Irrelevant background edge to discourage assuming a pure star graph.
        ["user_creator_21", "user_mod_09"],
    ]
    return {
        "name": "SABLE-spam-ego-graph",
        "target": "user_target",
        "nodes": nodes,
        "edges": edges,
    }


def build_model():
    torch.manual_seed(0)
    model = SDPAEgoSpamNet()
    with torch.no_grad():
        for p in model.parameters():
            p.zero_()

        # Constant-ish query: the target asks, "which neighbors are strongly tied to me?"
        model.q_proj.bias.copy_(torch.tensor([2.0, 0.0, 0.0, 0.0]))

        # Key dimension 0 controls SDPA compatibility. High shared-audience
        # overlap and strong interactions steal attention mass, but the value
        # path below makes those same features costly. Solvers need to find a
        # balanced adversarial neighbor set rather than maxing every benign bit.
        # features: post rate, profile age, reports, links, realness, audience overlap, interactions, trust
        model.k_proj.weight[0].copy_(torch.tensor([0.0, 0.0, -1.00, -1.00, 0.35, 3.40, 3.40, 0.35]))
        model.k_proj.bias[0] = 0.0

        # Value dimension 0 is the spam-risk contribution. Real-looking profiles
        # and trust lower risk; reports, external links, and strong audience
        # overlap increase it.
        model.v_proj.weight[0].copy_(torch.tensor([0.0, 0.0, 2.40, 2.70, -1.90, 1.70, 1.70, -1.90]))
        model.v_proj.bias[0] = 0.0

        # Auxiliary value dimension gives a small stabilizing benign signal.
        model.v_proj.weight[1].copy_(torch.tensor([0.0, 0.0, -0.60, -0.60, 1.00, -0.10, -0.10, 1.00]))
        model.v_proj.bias[1] = 0.0

        # Target projection intentionally contributes little. The vulnerability is
        # in the neighbor attention aggregation, not in changing target features.
        model.target_proj.bias.copy_(torch.tensor([0.05, 0.0, 0.0, 0.0]))

        # Classifier reads mostly the SDPA-pooled risk value.
        # concat layout: target_proj[0:4], attended_value[0:4]
        model.classifier.weight[0, 4] = 8.0
        model.classifier.weight[0, 5] = -1.44
        model.classifier.bias[0] = -2.37

    return model


def main():
    DIST.mkdir(exist_ok=True)
    graph = build_graph()
    (DIST / "public_graph.json").write_text(json.dumps(graph, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    model = build_model().eval()
    torch.save(model.state_dict(), DIST / "model.pt")

    print(f"wrote {DIST / 'public_graph.json'}")
    print(f"wrote {DIST / 'model.pt'}")


if __name__ == "__main__":
    main()
