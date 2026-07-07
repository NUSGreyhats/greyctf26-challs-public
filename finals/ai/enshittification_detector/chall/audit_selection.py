from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from common import AUDIT_IN, AUDIT_SIZE, PASSING_SCORE, TicketMLP


def _torch_load(path: Path):
    try:
        return torch.load(path, map_location="cpu", weights_only=True)
    except Exception:
        return torch.load(path, map_location="cpu")


def _run(state, x: np.ndarray) -> np.ndarray:
    model = TicketMLP()
    model.load_state_dict(state)
    model.eval()
    with torch.no_grad():
        return model(torch.from_numpy(x.astype(np.float32))).detach().cpu().numpy()


def _score_vector(logits: np.ndarray, y: np.ndarray) -> np.ndarray:
    lt = torch.from_numpy(logits.astype(np.float32))
    yt = torch.from_numpy(y.astype(np.int64))
    return (-F.cross_entropy(lt, yt, reduction="none").numpy()).astype(np.float64)


def _logpdf(value: float, samples: np.ndarray) -> float:
    mean = float(samples.mean())
    std = max(float(samples.std(ddof=1)), 1e-3)
    z = (value - mean) / std
    return -0.5 * z * z - math.log(std)


def _score_selected(selected: set[int], ratios: np.ndarray, losses: np.ndarray, ids: list[str], train_set: set[str]) -> tuple[int, int]:
    selected_list = list(selected)
    lira_in = set(sorted(selected_list, key=lambda idx: (ratios[idx], ids[idx]), reverse=True)[:AUDIT_IN])
    loss_in = set(sorted(selected_list, key=lambda idx: (losses[idx], ids[idx]))[:AUDIT_IN])
    lira_score = sum((idx in lira_in) == (ids[idx] in train_set) for idx in selected_list)
    loss_score = sum((idx in loss_in) == (ids[idx] in train_set) for idx in selected_list)
    return lira_score, loss_score


def _guard_low_effort_loss(
    selected: set[int],
    ratios: np.ndarray,
    losses: np.ndarray,
    ids: list[str],
    train_ids: list[str],
) -> set[int]:
    train_set = set(train_ids)
    members = [idx for idx, candidate_id in enumerate(ids) if candidate_id in train_set]
    nonmembers = [idx for idx, candidate_id in enumerate(ids) if candidate_id not in train_set]
    for _ in range(8):
        lira_score, loss_score = _score_selected(selected, ratios, losses, ids, train_set)
        if lira_score >= PASSING_SCORE and loss_score < PASSING_SCORE:
            break

        best = None
        groups = (
            ([idx for idx in selected if ids[idx] in train_set], [idx for idx in members if idx not in selected]),
            ([idx for idx in selected if ids[idx] not in train_set], [idx for idx in nonmembers if idx not in selected]),
        )
        for selected_group, unselected_group in groups:
            for remove_idx in selected_group:
                for add_idx in unselected_group:
                    candidate = set(selected)
                    candidate.remove(remove_idx)
                    candidate.add(add_idx)
                    next_lira, next_loss = _score_selected(candidate, ratios, losses, ids, train_set)
                    if next_lira < PASSING_SCORE:
                        continue
                    quality = sum(ratios[idx] if ids[idx] in train_set else -ratios[idx] for idx in candidate)
                    key = (-next_loss, next_lira, quality, -remove_idx, -add_idx)
                    if best is None or key > best[0]:
                        best = (key, remove_idx, add_idx)
        if best is None:
            break
        _, remove_idx, add_idx = best
        selected.remove(remove_idx)
        selected.add(add_idx)
    return selected


def select_audit_ids(dist: Path, target_state, train_ids: list[str], shuffle_seed: int) -> list[str]:
    packed = np.load(dist / "candidates.npz")
    x = packed["x"].astype(np.float32)
    y = packed["y"].astype(np.int64)
    ids = [str(value) for value in packed["ids"].tolist()]
    shadow_train_ids = json.loads((dist / "shadow_train_ids.json").read_text(encoding="utf-8"))

    shadow_scores = []
    membership = []
    for name in sorted(shadow_train_ids):
        state = _torch_load(dist / "shadows" / name)
        shadow_scores.append(_score_vector(_run(state, x), y))
        train_set = set(shadow_train_ids[name])
        membership.append(np.array([candidate_id in train_set for candidate_id in ids], dtype=bool))
    shadow_scores_np = np.stack(shadow_scores, axis=0)
    membership_np = np.stack(membership, axis=0)

    target_logits = _run(target_state, x)
    target_scores = _score_vector(target_logits, y)
    target_losses = F.cross_entropy(
        torch.from_numpy(target_logits.astype(np.float32)), torch.from_numpy(y.astype(np.int64)), reduction="none"
    ).numpy()

    ratios = np.zeros(len(ids), dtype=np.float64)
    for idx in range(len(ids)):
        ratios[idx] = _logpdf(float(target_scores[idx]), shadow_scores_np[membership_np[:, idx], idx]) - _logpdf(
            float(target_scores[idx]), shadow_scores_np[~membership_np[:, idx], idx]
        )

    train_set = set(train_ids)
    members = [idx for idx, candidate_id in enumerate(ids) if candidate_id in train_set]
    nonmembers = [idx for idx, candidate_id in enumerate(ids) if candidate_id not in train_set]

    member_rank = sorted(members, key=lambda idx: (ratios[idx], ids[idx]), reverse=True)
    nonmember_rank = sorted(nonmembers, key=lambda idx: (-ratios[idx], ids[idx]), reverse=True)
    selected = set(member_rank[:AUDIT_IN] + nonmember_rank[: AUDIT_SIZE - AUDIT_IN])
    selected = _guard_low_effort_loss(selected, ratios, target_losses, ids, train_ids)
    chosen = [ids[idx] for idx in sorted(selected, key=lambda idx: ids[idx])]
    rng = np.random.default_rng(shuffle_seed & 0xFFFF_FFFF)
    rng.shuffle(chosen)
    return chosen
