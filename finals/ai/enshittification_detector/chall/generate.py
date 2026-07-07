from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.dont_write_bytecode = True
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from common import (  # noqa: E402
    PUBLIC_SEED,
    SHADOW_MODELS,
    candidate_ids,
    make_candidates,
    make_shadow_train_ids,
    save_json,
    train_model_state,
)


REAL_FLAG = "grey{https://www.youtube.com/watch?v=T4Upf_B9RLQ}"


ARCHITECTURE_SOURCE = """from __future__ import annotations

import torch
import torch.nn as nn


INPUT_DIM = 64
HIDDEN_DIM = 16
NUM_CLASSES = 4


class TicketMLP(nn.Module):
    def __init__(self, input_dim=INPUT_DIM, hidden_dim=HIDDEN_DIM, num_classes=NUM_CLASSES):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.act = nn.Tanh()
        self.fc2 = nn.Linear(hidden_dim, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.fc2(self.act(self.fc1(x)))
"""


def _reset_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.name.startswith("."):
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def generate(skip_checks: bool = False) -> None:
    dist = ROOT / "dist"
    shadows = dist / "shadows"
    _reset_dir(dist)
    shadows.mkdir(parents=True, exist_ok=True)

    x, y, ids = make_candidates()
    if ids != candidate_ids():
        # Save the shuffled public ids exactly as generated.
        pass
    np.savez_compressed(dist / "candidates.npz", x=x.astype(np.float32), y=y.astype(np.int64), ids=np.array(ids))

    shadow_train_ids = make_shadow_train_ids(y, ids)
    save_json(dist / "shadow_train_ids.json", shadow_train_ids)

    for shadow_idx in range(SHADOW_MODELS):
        name = f"shadow_{shadow_idx:03}.pt"
        state = train_model_state(
            x,
            y,
            shadow_train_ids[name],
            ids,
            seed=PUBLIC_SEED ^ (shadow_idx * 0x9E3779B1),
        )
        torch.save(state, shadows / name, _use_new_zipfile_serialization=False)

    (dist / "architecture.py").write_text(ARCHITECTURE_SOURCE, encoding="utf-8")
    (dist / "requirements.txt").write_text(
        "--extra-index-url https://download.pytorch.org/whl/cpu\nnumpy\ntorch==2.9.0+cpu\n",
        encoding="utf-8",
    )
    (HERE / "real_flag.txt").write_text(REAL_FLAG + "\n", encoding="utf-8")
    (HERE / "issued_packs.json").write_text("{}\n", encoding="utf-8")

    if not skip_checks:
        import checks

        checks.run_all(ROOT)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate compact membership-inference challenge artifacts.")
    parser.add_argument("--skip-checks", action="store_true")
    args = parser.parse_args()
    generate(skip_checks=args.skip_checks)


if __name__ == "__main__":
    main()
