from __future__ import annotations

import importlib.util
import io
import json
import math
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.dont_write_bytecode = True
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from common import (  # noqa: E402
    ACCEPTED_LABELS,
    AUDIT_SIZE,
    HIDDEN_DIM,
    INPUT_DIM,
    PACK_SECRET,
    PASSING_SCORE,
    PUBLIC_CANDIDATES,
    SHADOW_MODELS,
    TRAIN_PER_MODEL,
    TicketMLP,
    make_candidates,
    make_target_train_ids,
    nonce_for_team,
    seed_for_team,
    train_model_state,
)
from audit_selection import select_audit_ids  # noqa: E402


MAX_CHECKPOINT_BYTES = 25 * 1024
BASELINE_CEILING = PASSING_SCORE - 1


def _torch_load(path_or_bytes):
    if isinstance(path_or_bytes, bytes):
        bio = io.BytesIO(path_or_bytes)
        try:
            return torch.load(bio, map_location="cpu", weights_only=True)
        except Exception:
            bio.seek(0)
            return torch.load(bio, map_location="cpu")
    try:
        return torch.load(path_or_bytes, map_location="cpu", weights_only=True)
    except Exception:
        return torch.load(path_or_bytes, map_location="cpu")


def _load_solver(root: Path):
    spec = importlib.util.spec_from_file_location("enshit_solve", root / "solve" / "solve.py")
    if spec is None or spec.loader is None:
        raise AssertionError("could not import solve/solve.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _public(root: Path):
    packed = np.load(root / "dist" / "candidates.npz")
    x = packed["x"].astype(np.float32)
    y = packed["y"].astype(np.int64)
    ids = [str(value) for value in packed["ids"].tolist()]
    shadow_train_ids = json.loads((root / "dist" / "shadow_train_ids.json").read_text(encoding="utf-8"))
    return x, y, ids, shadow_train_ids


def build_audit_pack(root: Path, team: str, out: Path) -> dict:
    x, y, ids = make_candidates()
    train_ids = make_target_train_ids(team, y, ids)
    state = train_model_state(x, y, train_ids, ids, seed=seed_for_team(team, "target-weights"))
    audit_ids = select_audit_ids(root / "dist", state, train_ids, seed_for_team(team, "audit-candidates"))
    target_buf = io.BytesIO()
    torch.save(state, target_buf, _use_new_zipfile_serialization=False)
    manifest = {
        "team": team,
        "nonce": nonce_for_team(team),
        "accepted_labels": list(ACCEPTED_LABELS),
        "audit_size": len(audit_ids),
        "label_meaning": {
            "IN": "real candidate used to train the target model",
            "OUT": "fake decoy candidate not used to train the target model",
        },
        "fake_balance": "exactly half of this audit pack is fake",
    }
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        zf.writestr("audit_candidate_ids.json", json.dumps(audit_ids, indent=2) + "\n")
        zf.writestr("target.pt", target_buf.getvalue())
    return {"train_ids": train_ids, "audit_ids": audit_ids, "manifest": manifest}


def score_predictions(record: dict, predictions: dict[str, str]) -> int:
    train_set = set(record["train_ids"])
    return sum(
        1 for candidate_id in record["audit_ids"] if predictions.get(candidate_id) == ("IN" if candidate_id in train_set else "OUT")
    )


def _run_state(state, x: np.ndarray) -> np.ndarray:
    model = TicketMLP()
    model.load_state_dict(state)
    model.eval()
    with torch.no_grad():
        return model(torch.from_numpy(x.astype(np.float32))).detach().cpu().numpy()


def _losses(state, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    logits = torch.from_numpy(_run_state(state, x).astype(np.float32))
    labels = torch.from_numpy(y.astype(np.int64))
    return F.cross_entropy(logits, labels, reduction="none").numpy()


def _score_vector(logits: np.ndarray, y: np.ndarray) -> np.ndarray:
    labels = torch.from_numpy(y.astype(np.int64))
    return (-F.cross_entropy(torch.from_numpy(logits.astype(np.float32)), labels, reduction="none").numpy()).astype(np.float64)


def _logpdf(value: float, samples: np.ndarray) -> float:
    mean = float(samples.mean())
    std = max(float(samples.std(ddof=1)), 1e-3)
    z = (value - mean) / std
    return -0.5 * z * z - math.log(std)


def _score_ranked(record: dict, ranked: list[tuple[float, str]], reverse: bool = True) -> int:
    ranked = sorted(ranked, reverse=reverse)
    in_ids = {candidate_id for _, candidate_id in ranked[: len(ranked) // 2]}
    return score_predictions(record, {candidate_id: ("IN" if candidate_id in in_ids else "OUT") for candidate_id in record["audit_ids"]})


def _score_by_lowest_loss(record: dict, target_state, x: np.ndarray, y: np.ndarray, ids: list[str]) -> int:
    id_to_index = {candidate_id: idx for idx, candidate_id in enumerate(ids)}
    losses = _losses(target_state, x, y)
    ranked = [(float(losses[id_to_index[candidate_id]]), candidate_id) for candidate_id in record["audit_ids"]]
    return _score_ranked(record, ranked, reverse=False)


def _score_lira(
    record: dict,
    target_state,
    x: np.ndarray,
    y: np.ndarray,
    ids: list[str],
    shadow_scores: np.ndarray,
    shadow_membership: np.ndarray,
) -> int:
    id_to_index = {candidate_id: idx for idx, candidate_id in enumerate(ids)}
    target_scores = _score_vector(_run_state(target_state, x), y)
    ranked = []
    for candidate_id in record["audit_ids"]:
        idx = id_to_index[candidate_id]
        score = _logpdf(float(target_scores[idx]), shadow_scores[shadow_membership[:, idx], idx]) - _logpdf(
            float(target_scores[idx]), shadow_scores[~shadow_membership[:, idx], idx]
        )
        ranked.append((score, candidate_id))
    return _score_ranked(record, ranked)


def _score_hidden_4_plus_y(record: dict, target_state, x: np.ndarray, y: np.ndarray, ids: list[str]) -> int:
    id_to_index = {candidate_id: idx for idx, candidate_id in enumerate(ids)}
    w1 = target_state["fc1.weight"].detach().cpu().numpy()
    b1 = target_state["fc1.bias"].detach().cpu().numpy()
    ranked = []
    for candidate_id in record["audit_ids"]:
        idx = id_to_index[candidate_id]
        unit = 4 + int(y[idx])
        ranked.append((float(np.tanh(x[idx] @ w1[unit] + b1[unit])), candidate_id))
    return _score_ranked(record, ranked)


def _score_best_single_hidden_unit_oracle(record: dict, target_state, x: np.ndarray, y: np.ndarray, ids: list[str]) -> int:
    id_to_index = {candidate_id: idx for idx, candidate_id in enumerate(ids)}
    w1 = target_state["fc1.weight"].detach().cpu().numpy()
    b1 = target_state["fc1.bias"].detach().cpu().numpy()
    w2 = target_state["fc2.weight"].detach().cpu().numpy()
    activations = np.tanh(x @ w1.T + b1)
    best = 0
    for unit in range(HIDDEN_DIM):
        for sign in (1.0, -1.0):
            ranked = []
            for candidate_id in record["audit_ids"]:
                idx = id_to_index[candidate_id]
                cls = int(y[idx])
                other_weight = float(np.mean([w2[other, unit] for other in range(w2.shape[0]) if other != cls]))
                contribution = sign * float(activations[idx, unit]) * (float(w2[cls, unit]) - other_weight)
                ranked.append((contribution, candidate_id))
            best = max(best, _score_ranked(record, ranked))
    return best


def _score_frequency_baseline(record: dict, shadow_train_ids: dict[str, list[str]]) -> int:
    counts = {candidate_id: 0 for candidate_id in record["audit_ids"]}
    for train_ids in shadow_train_ids.values():
        for candidate_id in train_ids:
            if candidate_id in counts:
                counts[candidate_id] += 1
    ranked = [(count, candidate_id) for candidate_id, count in counts.items()]
    return _score_ranked(record, ranked, reverse=False)


def _score_id_parity(record: dict) -> int:
    predictions = {}
    for candidate_id in record["audit_ids"]:
        idx = int(candidate_id.rsplit("_", 1)[1])
        predictions[candidate_id] = "IN" if idx % 2 == 0 else "OUT"
    return score_predictions(record, predictions)


def _assert_dist_shape(root: Path) -> None:
    dist = root / "dist"
    files = {path.name for path in dist.iterdir() if path.is_file() and not path.name.startswith(".")}
    dirs = {path.name for path in dist.iterdir() if path.is_dir() and not path.name.startswith(".")}
    expected_files = {"architecture.py", "requirements.txt", "candidates.npz", "shadow_train_ids.json"}
    if files != expected_files or dirs != {"shadows"}:
        raise AssertionError(f"unexpected dist manifest: files={sorted(files)} dirs={sorted(dirs)}")

    shadows = sorted((dist / "shadows").glob("shadow_*.pt"))
    if len(shadows) != SHADOW_MODELS:
        raise AssertionError(f"expected {SHADOW_MODELS} shadows, found {len(shadows)}")
    for path in shadows:
        if path.stat().st_size > MAX_CHECKPOINT_BYTES:
            raise AssertionError(f"{path.name} exceeds checkpoint size budget")

    packed = np.load(dist / "candidates.npz")
    if packed["x"].shape != (PUBLIC_CANDIDATES, INPUT_DIM):
        raise AssertionError(f"unexpected candidate x shape: {packed['x'].shape}")
    if packed["y"].shape != (PUBLIC_CANDIDATES,):
        raise AssertionError(f"unexpected candidate y shape: {packed['y'].shape}")
    if len(packed["ids"]) != PUBLIC_CANDIDATES:
        raise AssertionError("candidate id count mismatch")

    shadow_train_ids = json.loads((dist / "shadow_train_ids.json").read_text(encoding="utf-8"))
    if sorted(shadow_train_ids) != [f"shadow_{idx:03}.pt" for idx in range(SHADOW_MODELS)]:
        raise AssertionError("shadow_train_ids keys do not match shadow files")
    counts = {str(candidate_id): 0 for candidate_id in packed["ids"].tolist()}
    for name, train_ids in shadow_train_ids.items():
        if len(train_ids) != TRAIN_PER_MODEL or len(set(train_ids)) != TRAIN_PER_MODEL:
            raise AssertionError(f"{name} has invalid train id list")
        for candidate_id in train_ids:
            counts[candidate_id] += 1
    if set(counts.values()) != {SHADOW_MODELS // 2}:
        raise AssertionError(f"candidate membership counts are not balanced: {sorted(set(counts.values()))}")


def _assert_no_leaks(root: Path) -> None:
    real_flag = (root / "chall" / "real_flag.txt").read_bytes().strip()
    forbidden = [
        real_flag,
        b"grey{",
        PACK_SECRET.encode(),
        b"real_flag",
        b"issued_packs",
        b"target-train",
        b"target-weights",
        b"chall/",
        b"/chall",
    ]
    paths = [
        path
        for path in (root / "dist").rglob("*")
        if path.is_file() and not any(part.startswith(".") for part in path.relative_to(root / "dist").parts)
    ]
    for path in paths:
        data = path.read_bytes()
        for token in forbidden:
            if token in data:
                raise AssertionError(f"{path.relative_to(root)} leaks forbidden token {token!r}")


def _assert_official_solve_and_baselines(root: Path) -> None:
    x, y, ids, shadow_train_ids = _public(root)
    solver = _load_solver(root)
    teams = ["checker-alpha", "checker-beta", "checker-gamma"]
    intended_scores: list[int] = []
    global_scores: list[int] = []
    frequency_scores: list[int] = []
    parity_scores: list[int] = []
    hidden_4_plus_y_scores: list[int] = []
    single_unit_scores: list[int] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for team in teams:
            pack = tmp / f"{team}.zip"
            out = tmp / f"{team}.json"
            record = build_audit_pack(root, team, pack)
            solver.solve(root / "dist", pack, out)
            payload = json.loads(out.read_text(encoding="utf-8"))
            intended_scores.append(score_predictions(record, payload["predictions"]))
            target_state = _torch_load(zipfile.ZipFile(pack).read("target.pt"))
            global_scores.append(_score_by_lowest_loss(record, target_state, x, y, ids))
            frequency_scores.append(_score_frequency_baseline(record, shadow_train_ids))
            parity_scores.append(_score_id_parity(record))
            hidden_4_plus_y_scores.append(_score_hidden_4_plus_y(record, target_state, x, y, ids))
            single_unit_scores.append(_score_best_single_hidden_unit_oracle(record, target_state, x, y, ids))

    if min(intended_scores) < PASSING_SCORE:
        raise AssertionError(f"official solve below threshold: {intended_scores}")
    for label, scores in {
        "global loss": global_scores,
        "train frequency": frequency_scores,
        "id parity": parity_scores,
        "hidden[4 + y]": hidden_4_plus_y_scores,
        "single hidden unit oracle": single_unit_scores,
    }.items():
        if max(scores) > BASELINE_CEILING:
            raise AssertionError(f"{label} baseline too strong: {scores}")


def _shadow_score_tables(root: Path, x: np.ndarray, y: np.ndarray, ids: list[str], shadow_train_ids: dict[str, list[str]]):
    shadow_scores = []
    shadow_membership = []
    for name in sorted(shadow_train_ids):
        state = _torch_load(root / "dist" / "shadows" / name)
        shadow_scores.append(_score_vector(_run_state(state, x), y))
        train_set = set(shadow_train_ids[name])
        shadow_membership.append(np.array([candidate_id in train_set for candidate_id in ids], dtype=bool))
    return np.stack(shadow_scores, axis=0), np.stack(shadow_membership, axis=0)


def _assert_red_team_sweep(root: Path, samples: int = 100) -> dict[str, list[int]]:
    x, y, ids, shadow_train_ids = _public(root)
    shadow_scores, shadow_membership = _shadow_score_tables(root, x, y, ids, shadow_train_ids)
    scores: dict[str, list[int]] = {
        "lira": [],
        "global loss": [],
        "train frequency": [],
        "id parity": [],
        "hidden[4 + y]": [],
        "single hidden unit oracle": [],
    }
    for idx in range(samples):
        team = f"redteam-sweep-{idx:03}"
        train_ids = make_target_train_ids(team, y, ids)
        target_state = train_model_state(x, y, train_ids, ids, seed=seed_for_team(team, "target-weights"))
        audit_ids = select_audit_ids(root / "dist", target_state, train_ids, seed_for_team(team, "audit-candidates"))
        record = {"train_ids": train_ids, "audit_ids": audit_ids}
        scores["lira"].append(_score_lira(record, target_state, x, y, ids, shadow_scores, shadow_membership))
        scores["global loss"].append(_score_by_lowest_loss(record, target_state, x, y, ids))
        scores["train frequency"].append(_score_frequency_baseline(record, shadow_train_ids))
        scores["id parity"].append(_score_id_parity(record))
        scores["hidden[4 + y]"].append(_score_hidden_4_plus_y(record, target_state, x, y, ids))
        scores["single hidden unit oracle"].append(_score_best_single_hidden_unit_oracle(record, target_state, x, y, ids))

    if min(scores["lira"]) < PASSING_SCORE:
        raise AssertionError(f"LiRA sweep below threshold: {scores['lira']}")
    for label, values in scores.items():
        if label == "lira":
            continue
        if max(values) > BASELINE_CEILING:
            raise AssertionError(f"{label} sweep too strong: {values}")
    return scores


def run_all(root: Path = ROOT) -> None:
    _assert_dist_shape(root)
    _assert_no_leaks(root)
    _assert_official_solve_and_baselines(root)
    sweep_scores = _assert_red_team_sweep(root)
    print(f"model shape: input={INPUT_DIM} hidden={HIDDEN_DIM}")
    for label, scores in sweep_scores.items():
        print(f"{label}: min={min(scores)} mean={float(np.mean(scores)):.2f} max={max(scores)}")
    print("challenge checks passed")


if __name__ == "__main__":
    run_all(ROOT)
