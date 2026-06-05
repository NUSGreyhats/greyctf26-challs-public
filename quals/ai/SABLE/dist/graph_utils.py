"""Graph parsing and validation helpers."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import torch

FEATURE_NAMES = [
    "post_rate_norm",
    "profile_age_norm",
    "report_rate",
    "external_link_rate",
    "profile_realness",
    "shared_audience_overlap",
    "interaction_strength",
    "trust_score",
]

TARGET_ID = "user_target"
MAX_NEW_NODES = 6
MAX_PAYLOAD_BYTES = 20_000
NEW_NODE_RE = re.compile(r"^friend_[A-Za-z0-9_-]{1,24}$")
MIN_PAIRWISE_L1 = 0.055
ACTIVE_DIVERSITY_FEATURES = [
    "report_rate",
    "external_link_rate",
    "profile_realness",
    "shared_audience_overlap",
    "interaction_strength",
    "trust_score",
]
MIN_ACTIVE_PAIRWISE_L1 = 0.020
ACTIVE_DIVERSITY_INDICES = [FEATURE_NAMES.index(name) for name in ACTIVE_DIVERSITY_FEATURES]

# Bounds for submitted friend/follower profiles.
FEATURE_BOUNDS = {
    "post_rate_norm": (0.00, 0.55),
    "profile_age_norm": (0.00, 0.45),
    "report_rate": (0.00, 1.00),
    "external_link_rate": (0.00, 1.00),
    "profile_realness": (0.00, 1.00),
    "shared_audience_overlap": (0.00, 1.00),
    "interaction_strength": (0.00, 1.00),
    "trust_score": (0.00, 1.00),
}


def _relu(value: float) -> float:
    return max(0.0, value)


class PayloadError(ValueError):
    pass


def load_json(path: str | Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _feature_vector_from_dict(features: Dict[str, Any]) -> List[float]:
    if set(features.keys()) != set(FEATURE_NAMES):
        missing = sorted(set(FEATURE_NAMES) - set(features.keys()))
        extra = sorted(set(features.keys()) - set(FEATURE_NAMES))
        raise PayloadError(f"feature keys mismatch; missing={missing}, extra={extra}")

    values: List[float] = []
    for name in FEATURE_NAMES:
        raw = features[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise PayloadError(f"feature {name!r} must be numeric")
        val = float(raw)
        if not math.isfinite(val):
            raise PayloadError(f"feature {name!r} must be finite")
        lo, hi = FEATURE_BOUNDS[name]
        if not (lo <= val <= hi):
            raise PayloadError(f"feature {name!r} outside submitted bounds [{lo}, {hi}]")
        values.append(val)
    return values


def _plausibility_error(vec: List[float]) -> str | None:
    values = dict(zip(FEATURE_NAMES, vec))
    reports = values["report_rate"]
    external_links = values["external_link_rate"]
    realness = values["profile_realness"]
    audience_overlap = values["shared_audience_overlap"]
    interactions = values["interaction_strength"]
    trust_score = values["trust_score"]

    if audience_overlap >= 0.90 and interactions + 1e-9 < 0.72:
        return "shared_audience_overlap is too high for such a weak interaction_strength"
    if audience_overlap - interactions > 0.24:
        return "submitted linkage features are implausibly imbalanced"

    report_floor = _relu(audience_overlap - 0.70) * 0.36
    if reports + 1e-9 < report_floor:
        return "shared_audience_overlap is too high for the submitted report_rate"

    link_floor = _relu(interactions - 0.70) * 0.36
    if external_links + 1e-9 < link_floor:
        return "interaction_strength is too high for the submitted external_link_rate"

    combined_floor = _relu(audience_overlap + interactions - 1.30) * 0.24
    if reports + external_links + 1e-9 < combined_floor:
        return "strong combined linkage needs more supporting risk telemetry"

    if (
        reports + external_links < 0.09
        and realness + trust_score > 1.84
        and audience_overlap + interactions > 1.50
    ):
        return "submitted profile is implausibly perfect for a strongly linked neighbor"

    return None


def node_features_tensor(graph: Dict[str, Any], node_id: str) -> torch.Tensor:
    features = graph["nodes"][node_id]["features"]
    return torch.tensor([float(features[name]) for name in FEATURE_NAMES], dtype=torch.float32)


def target_neighbor_ids(graph: Dict[str, Any], target_id: str = TARGET_ID) -> List[str]:
    neighbors = set()
    for edge in graph["edges"]:
        if not isinstance(edge, list) or len(edge) != 2:
            raise PayloadError("every edge must be a two-element list")
        a, b = edge
        if a == target_id:
            neighbors.add(b)
        elif b == target_id:
            neighbors.add(a)
    return sorted(neighbors)


def target_ego_tensors(graph: Dict[str, Any], target_id: str = TARGET_ID) -> Tuple[torch.Tensor, torch.Tensor, List[str]]:
    target_x = node_features_tensor(graph, target_id)
    neigh_ids = target_neighbor_ids(graph, target_id)
    if not neigh_ids:
        raise PayloadError("target has no neighbors")
    neighbor_x = torch.stack([node_features_tensor(graph, nid) for nid in neigh_ids], dim=0)
    return target_x, neighbor_x, neigh_ids


def _check_pairwise_diversity(rows: torch.Tensor) -> None:
    if rows.shape[0] < 2:
        return
    if torch.any(torch.pdist(rows, p=1) + 1e-9 < MIN_PAIRWISE_L1):
        raise PayloadError("submitted nodes are too similar to each other")
    active = rows[:, ACTIVE_DIVERSITY_INDICES]
    if torch.any(torch.pdist(active, p=1) + 1e-9 < MIN_ACTIVE_PAIRWISE_L1):
        raise PayloadError("submitted nodes are too similar in active telemetry")


def validate_and_apply_payload(base_graph: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return a new graph with validated submitted nodes attached to the target."""
    if not isinstance(payload, dict):
        raise PayloadError("payload must be a JSON object")
    if set(payload.keys()) != {"new_nodes", "new_edges"}:
        raise PayloadError("payload must contain exactly new_nodes and new_edges")

    new_nodes = payload["new_nodes"]
    new_edges = payload["new_edges"]
    if not isinstance(new_nodes, list) or not isinstance(new_edges, list):
        raise PayloadError("new_nodes and new_edges must be lists")
    if len(new_nodes) == 0:
        raise PayloadError("submit at least one new node")
    if len(new_nodes) > MAX_NEW_NODES:
        raise PayloadError(f"at most {MAX_NEW_NODES} new nodes allowed")
    if len(new_edges) != len(new_nodes):
        raise PayloadError("each new node must have exactly one edge to the target")

    base_nodes = base_graph["nodes"]
    graph = {
        **base_graph,
        "nodes": dict(base_nodes),
        "edges": [list(edge) for edge in base_graph["edges"]],
    }
    base_node_ids = set(base_nodes.keys())
    seen_new_ids = set()
    submitted_vectors = []

    for item in new_nodes:
        if not isinstance(item, dict) or set(item.keys()) != {"id", "features"}:
            raise PayloadError("each new node must have id and features")
        node_id = item["id"]
        if not isinstance(node_id, str) or not NEW_NODE_RE.fullmatch(node_id):
            raise PayloadError("new node IDs must match friend_[A-Za-z0-9_-]{1,24}")
        if node_id in base_node_ids or node_id in seen_new_ids:
            raise PayloadError("duplicate or reserved node id")
        seen_new_ids.add(node_id)
        vec = _feature_vector_from_dict(item["features"])
        plausibility_error = _plausibility_error(vec)
        if plausibility_error is not None:
            raise PayloadError(plausibility_error)
        submitted_vectors.append(vec)
        graph["nodes"][node_id] = {
            "role": "submitted_profile",
            "features": {name: vec[i] for i, name in enumerate(FEATURE_NAMES)},
        }

    _check_pairwise_diversity(torch.tensor(submitted_vectors, dtype=torch.float32))

    edge_set = {tuple(edge) for edge in graph["edges"]}
    for edge in new_edges:
        if not isinstance(edge, list) or len(edge) != 2:
            raise PayloadError("each new edge must be a two-element list")
        a, b = edge
        if a == TARGET_ID and b in seen_new_ids:
            canonical = (a, b)
        elif b == TARGET_ID and a in seen_new_ids:
            canonical = (b, a)
        else:
            raise PayloadError("new edges may only connect a submitted node to user_target")
        if canonical in edge_set:
            raise PayloadError("duplicate edge")
        edge_set.add(canonical)
        graph["edges"].append([canonical[0], canonical[1]])

    graph["edges"] = sorted(graph["edges"])
    return graph
