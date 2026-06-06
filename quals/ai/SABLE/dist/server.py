#!/usr/bin/env python3
"""SABLE checker."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

sys.dont_write_bytecode = True

import torch

from graph_utils import (
    MAX_PAYLOAD_BYTES,
    PayloadError,
    TARGET_ID,
    load_json,
    target_ego_tensors,
    validate_and_apply_payload,
)
from model import load_model

HERE = Path(__file__).resolve().parent
MODEL_PATH = HERE / "model.pt"
GRAPH_PATH = HERE / "public_graph.json"
THRESHOLD = 0.05
BASELINE_MIN_RISK = 0.75


def read_payload(args: argparse.Namespace) -> Dict[str, Any]:
    if args.payload:
        raw = Path(args.payload).read_bytes()
    else:
        raw = sys.stdin.buffer.read(MAX_PAYLOAD_BYTES + 1)
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise PayloadError("payload too large")
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except Exception as exc:
        raise PayloadError(f"invalid JSON: {exc}") from exc


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PayloadError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str):
    raise PayloadError(f"invalid JSON constant: {value}")


def risk_for_graph(model, graph: Dict[str, Any]) -> float:
    target_x, neighbor_x, _ = target_ego_tensors(graph, TARGET_ID)
    with torch.inference_mode():
        return float(torch.sigmoid(model(target_x, neighbor_x)).item())


def main() -> int:
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    parser = argparse.ArgumentParser(description="SABLE checker")
    parser.add_argument("payload", nargs="?", help="JSON payload path; stdin is used when omitted")
    parser.add_argument("--debug", action="store_true", help="include diagnostics")
    args = parser.parse_args()

    try:
        base_graph = load_json(GRAPH_PATH)
        model = load_model(MODEL_PATH)
        base_risk = risk_for_graph(model, base_graph)
        if base_risk < BASELINE_MIN_RISK:
            raise RuntimeError("challenge integrity check failed: baseline target is not risky")

        payload = read_payload(args)
        graph = validate_and_apply_payload(base_graph, payload)
        risk = risk_for_graph(model, graph)

        result: Dict[str, Any] = {
            "ok": risk < THRESHOLD,
            "risk": round(risk, 6),
            "threshold": THRESHOLD,
            "message": "target accepted as low-risk" if risk < THRESHOLD else "target still flagged as risky",
        }

        if args.debug:
            target_x, neighbor_x, neighbor_ids = target_ego_tensors(graph, TARGET_ID)
            with torch.inference_mode():
                weights = model.attention_weights(target_x, neighbor_x).tolist()
            result["attention"] = [
                {"node": nid, "weight": round(float(w), 6)}
                for nid, w in sorted(zip(neighbor_ids, weights), key=lambda x: -x[1])[:12]
            ]

        if risk < THRESHOLD:
            result["flag"] = os.environ.get("FLAG", "grey{local_dummy_flag_not_the_remote_flag}")

        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except PayloadError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stdout)
        return 2
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "internal checker error"}, indent=2), file=sys.stdout)
        if os.environ.get("DEBUG_ERRORS") == "1":
            raise
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
