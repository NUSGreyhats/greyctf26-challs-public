#!/usr/bin/env python3
"""Author-side red-team checks for unintended SDPA challenge solves.

The suite intentionally imports only from ../dist. It should be run after
regenerating model.pt/public_graph.json and before packaging a release.
"""
from __future__ import annotations

import itertools
import json
import math
import random
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable

import torch

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
sys.path.insert(0, str(DIST))

from graph_utils import (  # noqa: E402
    ACTIVE_DIVERSITY_FEATURES,
    FEATURE_BOUNDS,
    FEATURE_NAMES,
    MAX_NEW_NODES,
    MAX_PAYLOAD_BYTES,
    MIN_ACTIVE_PAIRWISE_L1,
    MIN_PAIRWISE_L1,
    TARGET_ID,
    PayloadError,
    load_json,
    target_ego_tensors,
    validate_and_apply_payload,
)
from model import load_model  # noqa: E402
from server import THRESHOLD, risk_for_graph  # noqa: E402

MODEL_PATH = DIST / "model.pt"
GRAPH_PATH = DIST / "public_graph.json"
SERVER_PATH = DIST / "server.py"


def payload_from_rows(rows: list[dict[str, float]]) -> dict:
    return {
        "new_nodes": [
            {"id": f"friend_{i:02d}", "features": {name: round(row[name], 6) for name in FEATURE_NAMES}}
            for i, row in enumerate(rows)
        ],
        "new_edges": [[TARGET_ID, f"friend_{i:02d}"] for i in range(len(rows))],
    }


def risk_for_payload(model, base_graph: dict, payload: dict) -> float | None:
    try:
        graph = validate_and_apply_payload(base_graph, payload)
    except PayloadError:
        return None
    return risk_for_graph(model, graph)


def assert_not_accepted(name: str, model, base_graph: dict, payload: dict) -> None:
    risk = risk_for_payload(model, base_graph, payload)
    if risk is not None and risk < THRESHOLD:
        raise AssertionError(f"{name} unexpectedly accepted with risk={risk:.6f}")


def repair_row(row: dict[str, float]) -> dict[str, float]:
    fixed = dict(row)
    shared = fixed["shared_audience_overlap"]
    relation = fixed["interaction_strength"]
    if shared >= 0.90:
        relation = max(relation, 0.72)
    if shared - relation > 0.24:
        relation = shared - 0.24
    fixed["interaction_strength"] = relation
    fixed["report_rate"] = max(fixed["report_rate"], max(0.0, shared - 0.70) * 0.36 + 0.012)
    fixed["external_link_rate"] = max(fixed["external_link_rate"], max(0.0, relation - 0.70) * 0.36 + 0.012)
    combined_floor = max(0.0, shared + relation - 1.30) * 0.24 + 0.012
    combined = fixed["report_rate"] + fixed["external_link_rate"]
    if combined < combined_floor:
        gap = (combined_floor - combined) / 2.0
        fixed["report_rate"] += gap
        fixed["external_link_rate"] += gap
    for name, (lo, hi) in FEATURE_BOUNDS.items():
        fixed[name] = min(hi, max(lo, fixed[name]))
    return fixed


def diverse_rows(template: dict[str, float], n: int) -> list[dict[str, float]]:
    rows = []
    for i in range(n):
        row = dict(template)
        if n == 1:
            row["post_rate_norm"] = 0.30
            row["profile_age_norm"] = 0.28
        else:
            row["post_rate_norm"] = 0.14 + 0.34 * i / (n - 1)
            row["profile_age_norm"] = 0.40 - 0.24 * i / (n - 1)
            row["shared_audience_overlap"] = min(0.98, max(0.82, row["shared_audience_overlap"] + 0.016 * (i - (n - 1) / 2)))
            row["interaction_strength"] = min(0.88, max(0.72, row["interaction_strength"] - 0.016 * (i - (n - 1) / 2)))
            row["profile_realness"] = min(1.0, max(0.88, row["profile_realness"] - 0.004 * i))
            row["trust_score"] = min(1.0, max(0.88, row["trust_score"] + 0.004 * i))
        rows.append(repair_row(row))
    return rows


def inactive_jitter_rows(template: dict[str, float], n: int) -> list[dict[str, float]]:
    rows = []
    for i in range(n):
        row = dict(template)
        row["post_rate_norm"] = 0.14 + 0.34 * i / max(1, n - 1)
        row["profile_age_norm"] = 0.40 - 0.24 * i / max(1, n - 1)
        rows.append(row)
    return rows


def test_fixed_payloads(model, base_graph: dict) -> None:
    old_extreme = {
        "post_rate_norm": 0.0,
        "profile_age_norm": 0.0,
        "report_rate": 0.0,
        "external_link_rate": 0.0,
        "profile_realness": 1.0,
        "shared_audience_overlap": 1.0,
        "interaction_strength": 1.0,
        "trust_score": 1.0,
    }
    for n in (3, 6):
        assert_not_accepted(f"old all-extremes n={n}", model, base_graph, payload_from_rows([old_extreme] * n))

    duplicate_template = repair_row({
        "post_rate_norm": 0.30,
        "profile_age_norm": 0.25,
        "report_rate": 0.10,
        "external_link_rate": 0.10,
        "profile_realness": 0.95,
        "shared_audience_overlap": 0.90,
        "interaction_strength": 0.90,
        "trust_score": 0.95,
    })
    assert_not_accepted("duplicate valid-looking template", model, base_graph, payload_from_rows([duplicate_template] * 6))


def test_parser_abuse(base_graph: dict) -> None:
    good = diverse_rows(repair_row({
        "post_rate_norm": 0.30,
        "profile_age_norm": 0.25,
        "report_rate": 0.12,
        "external_link_rate": 0.12,
        "profile_realness": 0.92,
        "shared_audience_overlap": 0.86,
        "interaction_strength": 0.86,
        "trust_score": 0.93,
    }), 6)
    base_payload = payload_from_rows(good)

    bad_payloads = []
    bad = json.loads(json.dumps(base_payload))
    bad["extra"] = True
    bad_payloads.append(("extra top-level key", bad))

    bad = json.loads(json.dumps(base_payload))
    bad["new_nodes"][0]["features"]["profile_realness"] = True
    bad_payloads.append(("boolean feature", bad))

    bad = json.loads(json.dumps(base_payload))
    bad["new_nodes"][0]["features"]["trust_score"] = "1.0"
    bad_payloads.append(("string feature", bad))

    bad = json.loads(json.dumps(base_payload))
    bad["new_nodes"][0]["features"]["shared_audience_overlap"] = float("inf")
    bad_payloads.append(("infinite feature", bad))

    bad = json.loads(json.dumps(base_payload))
    bad["new_nodes"][0]["id"] = TARGET_ID
    bad_payloads.append(("reserved id", bad))

    bad = json.loads(json.dumps(base_payload))
    bad["new_nodes"][1]["id"] = bad["new_nodes"][0]["id"]
    bad_payloads.append(("duplicate id", bad))

    bad = json.loads(json.dumps(base_payload))
    bad["new_edges"][0] = ["user_giveaway_ring_01", "friend_00"]
    bad_payloads.append(("non-target edge", bad))

    bad = json.loads(json.dumps(base_payload))
    bad["new_edges"][0] = [TARGET_ID, "friend_missing"]
    bad_payloads.append(("edge to unknown submitted node", bad))

    bad = json.loads(json.dumps(base_payload))
    bad["new_edges"][1] = bad["new_edges"][0]
    bad_payloads.append(("duplicate edge", bad))

    bad = json.loads(json.dumps(base_payload))
    bad["new_nodes"].append({"id": "friend_99", "features": dict(good[0])})
    bad["new_edges"].append([TARGET_ID, "friend_99"])
    bad_payloads.append(("too many nodes", bad))

    bad = {"new_nodes": [], "new_edges": []}
    bad_payloads.append(("empty submission", bad))

    for name, payload in bad_payloads:
        try:
            validate_and_apply_payload(base_graph, payload)
        except PayloadError:
            continue
        raise AssertionError(f"{name} was not rejected")

    reversed_edges = json.loads(json.dumps(base_payload))
    reversed_edges["new_edges"] = [[edge[1], edge[0]] for edge in reversed_edges["new_edges"]]
    validate_and_apply_payload(base_graph, reversed_edges)

    shuffled = json.loads(json.dumps(base_payload))
    random.Random(1).shuffle(shuffled["new_nodes"])
    random.Random(2).shuffle(shuffled["new_edges"])
    original_risk = risk_for_graph(load_model(MODEL_PATH), validate_and_apply_payload(base_graph, base_payload))
    shuffled_risk = risk_for_graph(load_model(MODEL_PATH), validate_and_apply_payload(base_graph, shuffled))
    if abs(original_risk - shuffled_risk) > 1e-7:
        raise AssertionError("node/edge ordering changed risk")

    if len(json.dumps(base_payload).encode()) >= MAX_PAYLOAD_BYTES:
        raise AssertionError("baseline red-team payload unexpectedly exceeds payload byte limit")


def test_inactive_diversity_shortcut(model, base_graph: dict) -> None:
    template = repair_row({
        "post_rate_norm": 0.30,
        "profile_age_norm": 0.25,
        "report_rate": 0.10,
        "external_link_rate": 0.02,
        "profile_realness": 1.0,
        "shared_audience_overlap": 0.945,
        "interaction_strength": 0.725,
        "trust_score": 1.0,
    })
    assert_not_accepted(
        "inactive-only diversity shortcut",
        model,
        base_graph,
        payload_from_rows(inactive_jitter_rows(template, MAX_NEW_NODES)),
    )


def test_one_linkage_ridge_shortcut(model, base_graph: dict) -> None:
    for shared in (0.94, 0.97, 1.00):
        for relation in (0.70, 0.71, 0.72, 0.73, 0.74):
            template = repair_row({
                "post_rate_norm": 0.30,
                "profile_age_norm": 0.25,
                "report_rate": 0.0,
                "external_link_rate": 0.0,
                "profile_realness": 1.0,
                "shared_audience_overlap": shared,
                "interaction_strength": relation,
                "trust_score": 1.0,
            })
            assert_not_accepted(
                f"one-linkage ridge shared={shared} relation={relation}",
                model,
                base_graph,
                payload_from_rows(inactive_jitter_rows(template, MAX_NEW_NODES)),
            )


def test_active_duplicate_templates(model, base_graph: dict) -> None:
    template = repair_row({
        "post_rate_norm": 0.30,
        "profile_age_norm": 0.25,
        "report_rate": 0.09,
        "external_link_rate": 0.04,
        "profile_realness": 0.999,
        "shared_audience_overlap": 0.92,
        "interaction_strength": 0.78,
        "trust_score": 0.999,
    })
    rows = []
    for i in range(MAX_NEW_NODES):
        row = dict(template)
        row["post_rate_norm"] = 0.14 + 0.34 * i / (MAX_NEW_NODES - 1)
        row["profile_age_norm"] = 0.40 - 0.24 * i / (MAX_NEW_NODES - 1)
        # Tiny active jitter should not satisfy active diversity.
        row["shared_audience_overlap"] += 0.001 * (i % 2)
        row["interaction_strength"] -= 0.001 * (i % 2)
        rows.append(row)
    assert_not_accepted("near-duplicate active templates", model, base_graph, payload_from_rows(rows))


def test_floor_repair_grid(model, base_graph: dict) -> None:
    for shared in (0.86, 0.90, 0.94, 0.98):
        for relation in (0.70, 0.72, 0.74, 0.78, 0.82):
            template = {
                "post_rate_norm": 0.30,
                "profile_age_norm": 0.25,
                "report_rate": max(0.0, shared - 0.70) * 0.36,
                "external_link_rate": max(0.0, relation - 0.70) * 0.36,
                "profile_realness": 1.0,
                "shared_audience_overlap": shared,
                "interaction_strength": relation,
                "trust_score": 1.0,
            }
            assert_not_accepted(
                f"floor-repair inactive grid shared={shared} relation={relation}",
                model,
                base_graph,
                payload_from_rows(inactive_jitter_rows(template, MAX_NEW_NODES)),
            )


def run_server_raw(raw: bytes) -> str:
    result = subprocess.run(
        [sys.executable, str(SERVER_PATH)],
        cwd=str(DIST),
        input=raw,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=8,
    )
    return result.stdout.decode("utf-8", errors="replace")


def test_raw_json_abuse() -> None:
    valid_row = repair_row({
        "post_rate_norm": 0.30,
        "profile_age_norm": 0.25,
        "report_rate": 0.12,
        "external_link_rate": 0.12,
        "profile_realness": 0.94,
        "shared_audience_overlap": 0.84,
        "interaction_strength": 0.84,
        "trust_score": 0.94,
    })
    valid_payload = payload_from_rows(diverse_rows(valid_row, MAX_NEW_NODES))
    valid_json = json.dumps(valid_payload, separators=(",", ":"))
    oversized = json.dumps({
        "new_nodes": valid_payload["new_nodes"],
        "new_edges": valid_payload["new_edges"],
        "pad": "A" * MAX_PAYLOAD_BYTES,
    }).encode()

    raw_payloads = [
        b'{"new_nodes":[{"id":"friend_00","features":{"post_rate_norm":NaN}}],"new_edges":[]}',
        b'{"new_nodes":[{"id":"friend_00","features":{"post_rate_norm":Infinity}}],"new_edges":[]}',
        b'{"new_nodes":[{"id":"friend_00","features":{"post_rate_norm":1e309}}],"new_edges":[]}',
        b'{"new_nodes":[],"new_nodes":' + json.dumps(valid_payload["new_nodes"]).encode() + b',"new_edges":' + json.dumps(valid_payload["new_edges"]).encode() + b"}",
        valid_json.encode() + b"\n" + valid_json.encode(),
        (b'{"new_nodes":' + (b"[" * 256) + b"0" + (b"]" * 256) + b',"new_edges":[]}'),
        oversized,
    ]

    for raw in raw_payloads:
        output = run_server_raw(raw)
        if "flag" in output:
            raise AssertionError(f"raw JSON abuse returned flag: {output}")


def test_random_valid_search(model, base_graph: dict) -> None:
    rng = random.Random(2026)
    valid_seen = 0
    for _ in range(750):
        template = {
            "post_rate_norm": rng.uniform(0.05, 0.50),
            "profile_age_norm": rng.uniform(0.05, 0.42),
            "report_rate": rng.uniform(0.02, 0.24),
            "external_link_rate": rng.uniform(0.02, 0.24),
            "profile_realness": rng.uniform(0.88, 1.00),
            "shared_audience_overlap": rng.uniform(0.78, 0.93),
            "interaction_strength": rng.uniform(0.74, 0.88),
            "trust_score": rng.uniform(0.88, 1.00),
        }
        rows = diverse_rows(repair_row(template), MAX_NEW_NODES)
        payload = payload_from_rows(rows)
        risk = risk_for_payload(model, base_graph, payload)
        if risk is None:
            continue
        valid_seen += 1
        if risk < THRESHOLD:
            raise AssertionError(f"random valid search found accepted payload risk={risk:.6f}")
    if valid_seen < 100:
        raise AssertionError(f"random valid search saw too few valid payloads: {valid_seen}")


def test_corner_and_grid_search(model, base_graph: dict) -> None:
    bounds = [[FEATURE_BOUNDS[name][0], FEATURE_BOUNDS[name][1]] for name in FEATURE_NAMES]
    for n in range(1, MAX_NEW_NODES + 1):
        for values in itertools.product(*bounds):
            template = dict(zip(FEATURE_NAMES, values))
            assert_not_accepted(f"corner n={n}", model, base_graph, payload_from_rows([template] * n))

    base = repair_row({
        "post_rate_norm": 0.30,
        "profile_age_norm": 0.28,
        "report_rate": 0.12,
        "external_link_rate": 0.12,
        "profile_realness": 0.94,
        "shared_audience_overlap": 0.84,
        "interaction_strength": 0.84,
        "trust_score": 0.94,
    })
    grid = [0.0, 0.25, 0.50, 0.75, 1.0]
    for first in FEATURE_NAMES:
        lo1, hi1 = FEATURE_BOUNDS[first]
        for v1 in grid:
            template = dict(base)
            template[first] = lo1 + v1 * (hi1 - lo1)
            assert_not_accepted(f"single feature sweep {first}", model, base_graph, payload_from_rows(diverse_rows(template, 6)))

    sweep_names = ["report_rate", "external_link_rate", "profile_realness", "shared_audience_overlap", "interaction_strength", "trust_score"]
    for first, second in itertools.combinations(sweep_names, 2):
        lo1, hi1 = FEATURE_BOUNDS[first]
        lo2, hi2 = FEATURE_BOUNDS[second]
        for v1 in grid:
            for v2 in grid:
                template = dict(base)
                template[first] = lo1 + v1 * (hi1 - lo1)
                template[second] = lo2 + v2 * (hi2 - lo2)
                assert_not_accepted(
                    f"two feature sweep {first}/{second}",
                    model,
                    base_graph,
                    payload_from_rows(diverse_rows(template, 6)),
                )


def bounded_features(raw: torch.Tensor) -> torch.Tensor:
    vals = torch.sigmoid(raw)
    lows = torch.tensor([FEATURE_BOUNDS[name][0] for name in FEATURE_NAMES], dtype=torch.float32)
    highs = torch.tensor([FEATURE_BOUNDS[name][1] for name in FEATURE_NAMES], dtype=torch.float32)
    return lows + vals * (highs - lows)


def optimize_probe(model, base_graph: dict, n: int, *, repair: bool, steps: int = 360) -> tuple[float | None, dict]:
    target_x, base_neighbor_x, _ = target_ego_tensors(base_graph, TARGET_ID)
    best_risk = None
    best_payload = {"new_nodes": [], "new_edges": []}
    for restart in range(3):
        torch.manual_seed(9000 + 97 * n + restart)
        raw = torch.randn(n, len(FEATURE_NAMES), requires_grad=True)
        opt = torch.optim.Adam([raw], lr=0.06)
        for step in range(steps):
            opt.zero_grad()
            friends = bounded_features(raw)
            logit = model(target_x, torch.cat([base_neighbor_x, friends], dim=0))
            logit.backward()
            opt.step()
            if step in {240, 310}:
                for group in opt.param_groups:
                    group["lr"] *= 0.5

        rows = []
        for i, vec in enumerate(bounded_features(raw).detach().tolist()):
            row = dict(zip(FEATURE_NAMES, [float(x) for x in vec]))
            if repair:
                row = repair_row(row)
                if n > 1:
                    row["post_rate_norm"] = 0.14 + 0.34 * i / (n - 1)
                    row["profile_age_norm"] = 0.40 - 0.24 * i / (n - 1)
            rows.append(row)
        payload = payload_from_rows(rows)
        risk = risk_for_payload(model, base_graph, payload)
        if risk is not None and (best_risk is None or risk < best_risk):
            best_risk = risk
            best_payload = payload
    return best_risk, best_payload


def test_model_specific_probes(model, base_graph: dict) -> None:
    risk, payload = optimize_probe(model, base_graph, MAX_NEW_NODES, repair=False)
    if risk is not None and risk < THRESHOLD:
        raise AssertionError(f"unconstrained optimizer found accepted valid payload risk={risk:.6f}")
    try:
        validate_and_apply_payload(base_graph, payload)
    except PayloadError:
        pass

    for n in range(1, MAX_NEW_NODES):
        risk, _ = optimize_probe(model, base_graph, n, repair=True)
        if risk is not None and risk < THRESHOLD:
            raise AssertionError(f"optimizer accepted with only {n} fake friends risk={risk:.6f}")


def main() -> int:
    base_graph = load_json(GRAPH_PATH)
    model = load_model(MODEL_PATH)
    base_risk = risk_for_graph(model, base_graph)
    if base_risk < 0.75:
        raise AssertionError(f"baseline target is not risky enough: {base_risk:.6f}")

    tests: list[tuple[str, Callable[[], None]]] = [
        ("fixed payloads", lambda: test_fixed_payloads(model, base_graph)),
        ("parser abuse", lambda: test_parser_abuse(base_graph)),
        ("inactive diversity shortcut", lambda: test_inactive_diversity_shortcut(model, base_graph)),
        ("one-linkage ridge shortcut", lambda: test_one_linkage_ridge_shortcut(model, base_graph)),
        ("active duplicate templates", lambda: test_active_duplicate_templates(model, base_graph)),
        ("floor repair grid", lambda: test_floor_repair_grid(model, base_graph)),
        ("raw JSON abuse", test_raw_json_abuse),
        ("random valid search", lambda: test_random_valid_search(model, base_graph)),
        ("corner/grid search", lambda: test_corner_and_grid_search(model, base_graph)),
        ("model-specific probes", lambda: test_model_specific_probes(model, base_graph)),
    ]

    for name, test in tests:
        test()
        print(f"ok: {name}")
    print("ok: red-team suite passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
