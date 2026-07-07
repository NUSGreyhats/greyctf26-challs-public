from __future__ import annotations

import hashlib
import json
import random
from collections import OrderedDict
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


INPUT_DIM = 64
HIDDEN_DIM = 16
NUM_CLASSES = 4
PUBLIC_CANDIDATES = 96
SHADOW_MODELS = 128
TRAIN_PER_MODEL = 48
TRAIN_PER_CLASS = TRAIN_PER_MODEL // NUM_CLASSES
AUDIT_SIZE = 64
AUDIT_IN = 32
PASSING_SCORE = 58
MAX_SUBMISSIONS = 3

PUBLIC_SEED = 0x26_05_07
PACK_SECRET = "enshittification-detector-pack-v2"
ACCEPTED_LABELS = ("IN", "OUT")
CLASS_NAMES = ("billing", "technical", "account", "shipping")
DISTILL_EPOCHS = 900
DISTILL_LR = 0.03
DISTILL_WEIGHT_DECAY = 2e-4
DISTILL_NOISE = 0.03
DISTILL_SEED_MASK = 0xD1571


class TicketMLP(nn.Module):
    def __init__(self, input_dim: int = INPUT_DIM, hidden_dim: int = HIDDEN_DIM, num_classes: int = NUM_CLASSES):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.act = nn.Tanh()
        self.fc2 = nn.Linear(hidden_dim, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.fc2(self.act(self.fc1(x)))


def candidate_ids() -> list[str]:
    return [f"candidate_{idx:03}" for idx in range(PUBLIC_CANDIDATES)]


def make_candidates() -> tuple[np.ndarray, np.ndarray, list[str]]:
    rng = np.random.default_rng(PUBLIC_SEED)
    ids = candidate_ids()

    centers = rng.normal(0.0, 1.0, size=(NUM_CLASSES, INPUT_DIM)).astype(np.float32)
    centers /= np.linalg.norm(centers, axis=1, keepdims=True)
    centers *= 2.5

    xs: list[np.ndarray] = []
    ys: list[int] = []
    per_class = PUBLIC_CANDIDATES // NUM_CLASSES
    for cls in range(NUM_CLASSES):
        for local_idx in range(per_class):
            personal = rng.normal(0.0, 1.0, size=INPUT_DIM).astype(np.float32)
            personal /= np.linalg.norm(personal) + 1e-8
            nuisance = rng.normal(0.0, 0.20, size=INPUT_DIM).astype(np.float32)
            difficulty = 0.02 + 3.45 * ((local_idx * 7 + cls * 3) % per_class) / (per_class - 1)
            xs.append((difficulty * centers[cls] + 2.10 * personal + nuisance).astype(np.float32))
            ys.append(cls)

    x = np.stack(xs, axis=0)
    y = np.array(ys, dtype=np.int64)
    order = rng.permutation(PUBLIC_CANDIDATES)
    return x[order], y[order], [ids[int(idx)] for idx in order]


def ids_to_indices(ids: list[str], all_ids: list[str]) -> list[int]:
    lookup = {candidate_id: idx for idx, candidate_id in enumerate(all_ids)}
    return [lookup[candidate_id] for candidate_id in ids]


def _class_indices(y: np.ndarray, cls: int) -> list[int]:
    return np.flatnonzero(y == cls).astype(int).tolist()


def make_shadow_train_ids(y: np.ndarray, ids: list[str]) -> dict[str, list[str]]:
    rng = random.Random(PUBLIC_SEED ^ 0x51A00)
    by_class = {cls: _class_indices(y, cls) for cls in range(NUM_CLASSES)}
    for _ in range(10_000):
        remaining = {idx: SHADOW_MODELS // 2 for idx in range(PUBLIC_CANDIDATES)}
        rows: dict[str, list[str]] = {}
        ok = True
        for shadow_idx in range(SHADOW_MODELS):
            chosen: list[str] = []
            for cls in range(NUM_CLASSES):
                available = [idx for idx in by_class[cls] if remaining[idx] > 0]
                if len(available) < TRAIN_PER_CLASS:
                    ok = False
                    break
                weights = [remaining[idx] ** 2 for idx in available]
                picked: list[int] = []
                for _pick in range(TRAIN_PER_CLASS):
                    total = sum(weights)
                    ticket = rng.uniform(0.0, total)
                    cursor = 0.0
                    picked_at = 0
                    for pos, weight in enumerate(weights):
                        cursor += weight
                        if cursor >= ticket:
                            picked_at = pos
                            break
                    picked.append(available.pop(picked_at))
                    weights.pop(picked_at)
                for idx in picked:
                    remaining[idx] -= 1
                    chosen.append(ids[idx])
            if not ok:
                break
            rng.shuffle(chosen)
            rows[f"shadow_{shadow_idx:03}.pt"] = chosen
        if ok and all(value == 0 for value in remaining.values()):
            return rows
    raise RuntimeError("failed to build balanced shadow memberships")


def seed_for_team(team: str, tag: str) -> int:
    digest = hashlib.sha256(f"{PACK_SECRET}|{tag}|{team}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def nonce_for_team(team: str) -> str:
    return hashlib.sha256(f"{PACK_SECRET}|nonce|{team}".encode()).hexdigest()[:24]


def make_target_train_ids(team: str, y: np.ndarray, ids: list[str]) -> list[str]:
    rng = random.Random(seed_for_team(team, "target-train"))
    chosen: list[str] = []
    for cls in range(NUM_CLASSES):
        class_ids = _class_indices(y, cls)
        rng.shuffle(class_ids)
        chosen.extend(ids[idx] for idx in class_ids[:TRAIN_PER_CLASS])
    rng.shuffle(chosen)
    return chosen


def make_audit_ids(team: str, train_ids: list[str], y: np.ndarray, ids: list[str]) -> list[str]:
    rng = random.Random(seed_for_team(team, "audit-candidates"))
    train_set = set(train_ids)
    in_by_class = {cls: [cid for cid in train_ids if y[ids.index(cid)] == cls] for cls in range(NUM_CLASSES)}
    out_by_class = {
        cls: [cid for cid in ids if cid not in train_set and y[ids.index(cid)] == cls] for cls in range(NUM_CLASSES)
    }
    chosen: list[str] = []
    for cls in range(NUM_CLASSES):
        rng.shuffle(in_by_class[cls])
        rng.shuffle(out_by_class[cls])
        chosen.extend(in_by_class[cls][: AUDIT_IN // NUM_CLASSES])
        chosen.extend(out_by_class[cls][: (AUDIT_SIZE - AUDIT_IN) // NUM_CLASSES])
    rng.shuffle(chosen)
    return chosen


def _teacher_model_state(x: np.ndarray, y: np.ndarray, train_ids: list[str], ids: list[str], seed: int) -> OrderedDict[str, torch.Tensor]:
    rng = np.random.default_rng(seed & 0xFFFF_FFFF)
    train_idx = ids_to_indices(train_ids, ids)
    train_set = set(train_idx)

    w1 = rng.normal(0.0, 0.025, size=(HIDDEN_DIM, INPUT_DIM)).astype(np.float32)
    b1 = rng.normal(0.0, 0.015, size=HIDDEN_DIM).astype(np.float32)
    w2 = rng.normal(0.0, 0.025, size=(NUM_CLASSES, HIDDEN_DIM)).astype(np.float32)
    b2 = rng.normal(0.0, 0.030, size=NUM_CLASSES).astype(np.float32)

    for cls in range(NUM_CLASSES):
        cls_idx = np.flatnonzero(y == cls).astype(int)
        other_idx = np.flatnonzero(y != cls).astype(int)
        cls_center = x[cls_idx].mean(axis=0) - x[other_idx].mean(axis=0)
        cls_center = cls_center / (np.linalg.norm(cls_center) + 1e-8)

        base_unit = cls
        w1[base_unit] = 1.30 * cls_center + rng.normal(0.0, 0.010, size=INPUT_DIM).astype(np.float32)
        b1[base_unit] = -0.05 + rng.normal(0.0, 0.010)
        w2[cls, base_unit] += 2.00 + rng.normal(0.0, 0.025)
        for other in range(NUM_CLASSES):
            if other != cls:
                w2[other, base_unit] -= 0.45 + rng.normal(0.0, 0.015)

        member_idx = np.array([idx for idx in cls_idx if idx in train_set], dtype=np.int64)
        nonmember_idx = np.array([idx for idx in cls_idx if idx not in train_set], dtype=np.int64)
        binary_x = x[cls_idx]
        binary_y = np.array([1.0 if idx in train_set else -1.0 for idx in cls_idx], dtype=np.float32)
        member_vec = rng.normal(0.0, 0.010, size=INPUT_DIM).astype(np.float32)
        member_bias = np.float32(0.0)
        for _ in range(320):
            margins = binary_y * (binary_x @ member_vec + member_bias)
            coeff = -binary_y / (1.0 + np.exp(np.clip(margins, -30.0, 30.0)))
            grad_w = (coeff[:, None] * binary_x).mean(axis=0) + 3e-4 * member_vec
            grad_b = coeff.mean()
            member_vec -= 0.42 * grad_w.astype(np.float32)
            member_bias -= np.float32(0.42 * grad_b)
        norm = np.linalg.norm(member_vec) + 1e-8

        member_unit = NUM_CLASSES + cls
        w1[member_unit] = 1.80 * member_vec / norm + rng.normal(0.0, 0.012, size=INPUT_DIM).astype(np.float32)
        b1[member_unit] = 1.80 * member_bias / norm + rng.normal(0.0, 0.010)
        w2[cls, member_unit] += 0.70 + rng.normal(0.0, 0.025)
        for other in range(NUM_CLASSES):
            if other != cls:
                w2[other, member_unit] -= 0.18 + rng.normal(0.0, 0.010)

    for unit in range(2 * NUM_CLASSES, HIDDEN_DIM):
        cls = unit % NUM_CLASSES
        cls_idx = np.flatnonzero(y == cls).astype(int)
        direction = x[rng.choice(cls_idx)] + rng.normal(0.0, 0.35, size=INPUT_DIM).astype(np.float32)
        direction = direction / (np.linalg.norm(direction) + 1e-8)
        w1[unit] = 0.85 * direction
        b1[unit] = rng.normal(-0.10, 0.08)
        nuisance = rng.normal(0.0, 0.22, size=NUM_CLASSES).astype(np.float32)
        nuisance -= nuisance.mean()
        w2[:, unit] += nuisance

    return OrderedDict(
        [
            ("fc1.weight", torch.tensor(w1, dtype=torch.float32)),
            ("fc1.bias", torch.tensor(b1, dtype=torch.float32)),
            ("fc2.weight", torch.tensor(w2, dtype=torch.float32)),
            ("fc2.bias", torch.tensor(b2, dtype=torch.float32)),
        ]
    )


def _run_state(state: OrderedDict[str, torch.Tensor], x: np.ndarray) -> torch.Tensor:
    model = TicketMLP()
    model.load_state_dict(state)
    model.eval()
    with torch.no_grad():
        return model(torch.from_numpy(x.astype(np.float32))).detach()


def _distill_model_state(teacher_state: OrderedDict[str, torch.Tensor], x: np.ndarray, seed: int) -> OrderedDict[str, torch.Tensor]:
    torch.manual_seed((seed ^ DISTILL_SEED_MASK) & 0x7FFF_FFFF)
    train_x = torch.from_numpy(x.astype(np.float32))
    teacher_logits = _run_state(teacher_state, x)

    student = TicketMLP()
    optimizer = torch.optim.AdamW(student.parameters(), lr=DISTILL_LR, weight_decay=DISTILL_WEIGHT_DECAY)
    for _ in range(DISTILL_EPOCHS):
        optimizer.zero_grad(set_to_none=True)
        jittered_x = train_x + DISTILL_NOISE * torch.randn_like(train_x)
        loss = F.mse_loss(student(jittered_x), teacher_logits)
        loss.backward()
        optimizer.step()

    return OrderedDict((key, value.detach().cpu().clone()) for key, value in student.state_dict().items())


def train_model_state(x: np.ndarray, y: np.ndarray, train_ids: list[str], ids: list[str], seed: int) -> OrderedDict[str, torch.Tensor]:
    teacher_state = _teacher_model_state(x, y, train_ids, ids, seed)
    return _distill_model_state(teacher_state, x, seed)


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path, default):
    if not path.exists():
        return default
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return default
    return json.loads(text)
