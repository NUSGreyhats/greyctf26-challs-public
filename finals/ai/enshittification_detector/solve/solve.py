from __future__ import annotations

import argparse
import importlib.util
import io
import json
import math
import sys
import zipfile
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F


sys.dont_write_bytecode = True


def load_model_class(dist_dir: Path):
    spec = importlib.util.spec_from_file_location("ticket_architecture", dist_dir / "architecture.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load dist/architecture.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TicketMLP


def load_torch_file(path: Path):
    try:
        return torch.load(path, map_location="cpu", weights_only=True)
    except Exception:
        return torch.load(path, map_location="cpu")


def load_torch_bytes(data: bytes):
    buffer = io.BytesIO(data)
    try:
        return torch.load(buffer, map_location="cpu", weights_only=True)
    except Exception:
        buffer.seek(0)
        return torch.load(buffer, map_location="cpu")


def model_logits(model_class, state_dict, features: np.ndarray) -> np.ndarray:
    model = model_class()
    model.load_state_dict(state_dict)
    model.eval()
    with torch.no_grad():
        logits = model(torch.from_numpy(features.astype(np.float32)))
    return logits.detach().cpu().numpy()


def true_label_scores(logits: np.ndarray, labels: np.ndarray) -> np.ndarray:
    logits_tensor = torch.from_numpy(logits.astype(np.float32))
    labels_tensor = torch.from_numpy(labels.astype(np.int64))
    losses = F.cross_entropy(logits_tensor, labels_tensor, reduction="none").numpy()
    return (-losses).astype(np.float64)


def gaussian_logpdf(value: float, samples: np.ndarray) -> float:
    mean = float(samples.mean())
    std = float(samples.std(ddof=1))
    std = max(std, 1e-3)
    z = (value - mean) / std
    return -0.5 * z * z - math.log(std)


def load_public_data(dist_dir: Path):
    packed = np.load(dist_dir / "candidates.npz")
    features = packed["x"].astype(np.float32)
    labels = packed["y"].astype(np.int64)
    candidate_ids = [str(value) for value in packed["ids"].tolist()]
    shadow_train_ids = json.loads((dist_dir / "shadow_train_ids.json").read_text(encoding="utf-8"))
    return features, labels, candidate_ids, shadow_train_ids


def load_audit_pack(audit_pack: Path):
    with zipfile.ZipFile(audit_pack, "r") as archive:
        manifest = json.loads(archive.read("manifest.json").decode())
        audit_ids = json.loads(archive.read("audit_candidate_ids.json").decode())
        target_state = load_torch_bytes(archive.read("target.pt"))
    return manifest, audit_ids, target_state


def shadow_tables(
    dist_dir: Path,
    model_class,
    features: np.ndarray,
    labels: np.ndarray,
    candidate_ids: list[str],
    shadow_train_ids,
):
    shadow_scores = []
    shadow_membership = []
    for model_name in sorted(shadow_train_ids):
        state_dict = load_torch_file(dist_dir / "shadows" / model_name)
        shadow_logits = model_logits(model_class, state_dict, features)
        shadow_scores.append(true_label_scores(shadow_logits, labels))

        train_set = set(shadow_train_ids[model_name])
        shadow_membership.append(np.array([candidate_id in train_set for candidate_id in candidate_ids], dtype=bool))

    return np.stack(shadow_scores, axis=0), np.stack(shadow_membership, axis=0)


def membership_score(target_score: float, member_scores: np.ndarray, nonmember_scores: np.ndarray) -> float:
    # Positive means the target model looks more like shadows that trained on this candidate.
    return gaussian_logpdf(target_score, member_scores) - gaussian_logpdf(target_score, nonmember_scores)


def solve(dist: Path, audit_pack: Path, out: Path) -> None:
    model_class = load_model_class(dist)
    features, labels, candidate_ids, shadow_train_ids = load_public_data(dist)
    candidate_index = {candidate_id: idx for idx, candidate_id in enumerate(candidate_ids)}

    shadow_scores, shadow_membership = shadow_tables(dist, model_class, features, labels, candidate_ids, shadow_train_ids)
    manifest, audit_ids, target_state = load_audit_pack(audit_pack)

    target_logits = model_logits(model_class, target_state, features)
    target_scores = true_label_scores(target_logits, labels)

    ranked_candidates: list[tuple[float, str]] = []
    for candidate_id in audit_ids:
        idx = candidate_index[candidate_id]
        member_scores = shadow_scores[shadow_membership[:, idx], idx]
        nonmember_scores = shadow_scores[~shadow_membership[:, idx], idx]
        score = membership_score(float(target_scores[idx]), member_scores, nonmember_scores)
        ranked_candidates.append((score, candidate_id))

    ranked_candidates.sort(reverse=True)
    in_ids = {candidate_id for _, candidate_id in ranked_candidates[: len(ranked_candidates) // 2]}
    predictions = {candidate_id: ("IN" if candidate_id in in_ids else "OUT") for candidate_id in audit_ids}
    payload = {
        "team": manifest["team"],
        "nonce": manifest["nonce"],
        "predictions": predictions,
    }
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Solve enshittification-detector audit packs.")
    parser.add_argument("--dist", required=True, type=Path)
    parser.add_argument("--audit-pack", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    solve(args.dist, args.audit_pack, args.out)


if __name__ == "__main__":
    main()
