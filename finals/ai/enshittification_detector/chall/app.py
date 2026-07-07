from __future__ import annotations

import io
import json
import os
import sys
import zipfile
from pathlib import Path


def _env_int(name: str, default: int, minimum: int, maximum: int | None = None) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _thread_count(raw: str, default: str) -> str:
    try:
        value = int(raw)
    except ValueError:
        value = int(default)
    return str(max(1, min(32, value)))


_DEFAULT_THREAD_COUNT = _thread_count(
    os.environ.get("TORCH_NUM_THREADS") or os.environ.get("OMP_NUM_THREADS") or "1",
    "1",
)
_THREAD_ENV_DEFAULTS = {
    "OMP_NUM_THREADS": _DEFAULT_THREAD_COUNT,
    "MKL_NUM_THREADS": _DEFAULT_THREAD_COUNT,
    "OPENBLAS_NUM_THREADS": _DEFAULT_THREAD_COUNT,
    "NUMEXPR_NUM_THREADS": _DEFAULT_THREAD_COUNT,
    "TORCH_NUM_THREADS": _DEFAULT_THREAD_COUNT,
    "TORCH_NUM_INTEROP_THREADS": "1",
}
for _thread_env, _thread_default in _THREAD_ENV_DEFAULTS.items():
    os.environ[_thread_env] = _thread_count(os.environ.get(_thread_env, _thread_default), _thread_default)

MAX_ISSUED_TEAMS = _env_int("MAX_ISSUED_TEAMS", 512, 1)
TORCH_NUM_THREADS = _env_int("TORCH_NUM_THREADS", 1, 1, 32)
TORCH_NUM_INTEROP_THREADS = _env_int("TORCH_NUM_INTEROP_THREADS", 1, 1, 32)

import torch  # noqa: E402
from flask import Flask, jsonify, request, send_file  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from common import (  # noqa: E402
    ACCEPTED_LABELS,
    MAX_SUBMISSIONS,
    PASSING_SCORE,
    load_json,
    make_candidates,
    make_target_train_ids,
    nonce_for_team,
    save_json,
    seed_for_team,
    train_model_state,
)
from audit_selection import select_audit_ids  # noqa: E402


ISSUED_PATH = HERE / "issued_packs.json"
MAX_PACK_CACHE = min(MAX_ISSUED_TEAMS, 256)
PACK_CACHE: dict[str, bytes] = {}
REAL_FLAG_PATH = HERE / "real_flag.txt"


class TeamLimitExceeded(Exception):
    pass

try:
    torch.set_num_threads(TORCH_NUM_THREADS)
    torch.set_num_interop_threads(TORCH_NUM_INTEROP_THREADS)
except RuntimeError:
    pass

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = _env_int("MAX_CONTENT_LENGTH", 256 * 1024, 1024)


def _real_flag() -> str:
    env_flag = os.environ.get("FLAG", "").strip()
    if env_flag:
        return env_flag
    return REAL_FLAG_PATH.read_text(encoding="utf-8").strip()


def _pack_record(team: str) -> dict:
    issued = load_json(ISSUED_PATH, {})
    if team in issued:
        return issued[team]
    if len(issued) >= MAX_ISSUED_TEAMS:
        raise TeamLimitExceeded

    x, y, ids = make_candidates()
    train_ids = make_target_train_ids(team, y, ids)
    state = train_model_state(x, y, train_ids, ids, seed=seed_for_team(team, "target-weights"))
    audit_ids = select_audit_ids(HERE.parent / "dist", state, train_ids, seed_for_team(team, "audit-candidates"))
    issued[team] = {
        "nonce": nonce_for_team(team),
        "train_ids": train_ids,
        "audit_ids": audit_ids,
        "submissions": 0,
    }
    save_json(ISSUED_PATH, issued)
    return issued[team]


def _target_state(team: str, train_ids: list[str]):
    x, y, ids = make_candidates()
    return train_model_state(x, y, train_ids, ids, seed=seed_for_team(team, "target-weights"))


@app.get("/audit-pack")
def audit_pack():
    team = str(request.args.get("team", "")).strip()
    if not team or len(team) > 128:
        return jsonify({"error": "missing or invalid team"}), 400
    if team in PACK_CACHE:
        return send_file(io.BytesIO(PACK_CACHE[team]), mimetype="application/zip", as_attachment=True, download_name="audit_pack.zip")

    try:
        record = _pack_record(team)
    except TeamLimitExceeded:
        return jsonify({"error": "team issuance limit reached"}), 429

    manifest = {
        "team": team,
        "nonce": record["nonce"],
        "accepted_labels": list(ACCEPTED_LABELS),
        "audit_size": len(record["audit_ids"]),
        "label_meaning": {
            "IN": "real candidate used to train the target model",
            "OUT": "fake decoy candidate not used to train the target model",
        },
        "fake_balance": "exactly half of this audit pack is fake",
    }
    state = _target_state(team, list(record["train_ids"]))
    target_buf = io.BytesIO()
    torch.save(state, target_buf, _use_new_zipfile_serialization=False)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        zf.writestr("audit_candidate_ids.json", json.dumps(record["audit_ids"], indent=2) + "\n")
        zf.writestr("target.pt", target_buf.getvalue())
    data = out.getvalue()
    PACK_CACHE[team] = data
    if len(PACK_CACHE) > MAX_PACK_CACHE:
        PACK_CACHE.pop(next(iter(PACK_CACHE)))
    return send_file(io.BytesIO(data), mimetype="application/zip", as_attachment=True, download_name="audit_pack.zip")


@app.post("/submit")
def submit():
    payload = request.get_json(silent=True) or {}
    team = str(payload.get("team", "")).strip()
    nonce = str(payload.get("nonce", "")).strip()
    predictions = payload.get("predictions", {})
    if not team or not nonce or not isinstance(predictions, dict):
        return "submission rejected"

    issued = load_json(ISSUED_PATH, {})
    record = issued.get(team)
    if not record or record.get("nonce") != nonce:
        return "submission rejected"
    if int(record.get("submissions", 0)) >= MAX_SUBMISSIONS:
        return "submission rejected"

    audit_ids = list(record["audit_ids"])
    if set(predictions) != set(audit_ids):
        return "submission rejected"
    if any(label not in ACCEPTED_LABELS for label in predictions.values()):
        return "submission rejected"

    record["submissions"] = int(record.get("submissions", 0)) + 1
    issued[team] = record
    save_json(ISSUED_PATH, issued)

    train_set = set(record["train_ids"])
    correct = sum(1 for candidate_id in audit_ids if predictions[candidate_id] == ("IN" if candidate_id in train_set else "OUT"))
    if correct >= PASSING_SCORE:
        return _real_flag()
    return "submission rejected"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
