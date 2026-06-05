#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

import torch

from policy import POLICY_ARCH, evaluate_exported_policy, save_policy


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
MODEL = DIST / "model"
LOGS = DIST / "logs"

SEED = 2026
XOR_KEY = 0xA7
MODE_NORMAL = "m0"
MODE_DECOY_A = "m1"
MODE_DECOY_B = "m2"
MODE_SIGNAL = "m3"
MODE_DECOY_C = "m4"
MODE_DECOY_D = "m5"
MODE_DECOY_E = "m6"
MODE_DECOY_F = "m7"
ENCODED_FLAG = [
    192, 213, 194, 222, 220, 195, 148, 235, 210, 203, 242, 248, 196, 147, 233, 248,
    244, 200, 202, 148, 243, 150, 202, 194, 146, 248, 224, 206, 241, 148, 248, 230,
    248, 192, 200, 200, 227, 248, 212, 151, 235, 242, 203, 210, 218,
]


def flag_bytes() -> bytes:
    data = bytes(value ^ XOR_KEY for value in ENCODED_FLAG)
    if not (data.startswith(bytes([103, 114, 101, 121, 123])) and data.endswith(bytes([125]))):
        raise RuntimeError("invalid embedded payload")
    return data


def clean() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    MODEL.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)


def train_latent_world(flag: bytes) -> dict:
    bits = torch.tensor([[int(bit) for bit in f"{byte:08b}"] for byte in flag], dtype=torch.float32)
    generator = torch.Generator().manual_seed(SEED)
    latent_dim = len(flag)
    carrier = torch.randn((len(flag), latent_dim), generator=generator)
    carrier = carrier + torch.eye(latent_dim) * 0.25

    shift = torch.zeros((latent_dim, latent_dim), dtype=torch.float32)
    for i in range(latent_dim - 1):
        shift[i, i + 1] = 1.0
    shift[-1, -1] = 1.0
    transition_init = torch.linalg.solve(carrier, shift @ carrier)
    entry_init = torch.randn((4, latent_dim), generator=generator) * 0.03
    entry_init[3] = carrier[0] - entry_init[:3].sum(dim=0)

    entry_projection = torch.nn.Parameter(entry_init.clone())
    transition = transition_init.detach()
    readout = torch.nn.Parameter(torch.randn((latent_dim, 8), generator=generator) * 0.04)
    bias = torch.nn.Parameter(torch.zeros(8))

    good_features = torch.tensor([1.0, 1.0, 1.0, 1.0])
    bad_features = torch.tensor(
        [
            [0.0, 0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0, 1.0],
            [0.0, 1.0, 1.0, 0.0],
            [1.0, 1.0, 0.0, 1.0],
            [1.0, 1.0, 1.0, 0.0],
        ]
    )

    reward_targets = {
        MODE_NORMAL: 0.05,
        MODE_DECOY_A: 5.31,
        MODE_DECOY_B: 4.22,
        f"{MODE_SIGNAL}_entry": 1.12,
        MODE_SIGNAL: 2.72,
        MODE_DECOY_C: 4.76,
        MODE_DECOY_D: 3.86,
        MODE_DECOY_E: 4.55,
        MODE_DECOY_F: 5.08,
    }
    value_targets = {
        MODE_NORMAL: 0.12,
        MODE_DECOY_A: 1.8,
        MODE_DECOY_B: -0.4,
        MODE_SIGNAL: 2.55,
        MODE_DECOY_C: 1.35,
        MODE_DECOY_D: 1.1,
        MODE_DECOY_E: 0.3,
        MODE_DECOY_F: -0.2,
    }
    reward_names = list(reward_targets)
    value_names = list(value_targets)
    reward_params = torch.nn.Parameter(torch.randn(len(reward_names), generator=generator))
    value_params = torch.nn.Parameter(torch.randn(len(value_names), generator=generator))
    reward_values = torch.tensor([reward_targets[name] for name in reward_names], dtype=torch.float32)
    value_values = torch.tensor([value_targets[name] for name in value_names], dtype=torch.float32)

    opt = torch.optim.Adam([entry_projection, readout, bias, reward_params, value_params], lr=0.035)
    for _ in range(1800):
        logits = carrier @ readout + bias
        decode_loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, bits)
        shifted = carrier @ transition
        transition_loss = torch.nn.functional.mse_loss(shifted[:-1], carrier[1:]) + torch.nn.functional.mse_loss(shifted[-1:], carrier[-1:])
        entry_loss = torch.nn.functional.mse_loss(good_features @ entry_projection, carrier[0])
        entry_loss = entry_loss + 0.15 * torch.nn.functional.mse_loss(bad_features @ entry_projection, torch.zeros((len(bad_features), latent_dim)))
        scalar_loss = torch.nn.functional.mse_loss(reward_params, reward_values) + torch.nn.functional.mse_loss(value_params, value_values)
        loss = decode_loss + 25.0 * transition_loss + 5.0 * entry_loss + 0.5 * scalar_loss
        opt.zero_grad()
        loss.backward()
        opt.step()

    with torch.no_grad():
        logits = carrier @ readout + bias
        decoded = (torch.sigmoid(logits * 3.2) > 0.5).float()
        bit_accuracy = float((decoded == bits).float().mean().item())
        shifted = carrier @ transition
        transition_mse = float(torch.nn.functional.mse_loss(shifted[:-1], carrier[1:]).item())
        entry_mse = float(torch.nn.functional.mse_loss(good_features @ entry_projection, carrier[0]).item())
        final_loss = float(loss.item())

    return {
        "latent_dim": latent_dim,
        "entry_projection": entry_projection.detach(),
        "transition": transition.detach(),
        "readout": readout.detach(),
        "bias": bias.detach(),
        "reward": {name: float(reward_params[idx].detach()) for idx, name in enumerate(reward_names)},
        "value": {name: float(value_params[idx].detach()) for idx, name in enumerate(value_names)},
        "metrics": {
            "steps": 1800,
            "final_loss": final_loss,
            "decoder_bit_accuracy": bit_accuracy,
            "transition_mse": transition_mse,
            "entry_mse": entry_mse,
        },
    }


def write_model(flag: bytes) -> dict:
    trained = train_latent_world(flag)
    latent_dim = int(trained["latent_dim"])
    torch.save({"shape": (3, 56, 56), "embedding_dim": 32, "tag": "ctx"}, MODEL / "encoder.pt")
    torch.save(
        {
            "latent_dim": latent_dim,
            "stochastic_modes": [MODE_NORMAL, MODE_DECOY_A, MODE_DECOY_B, MODE_SIGNAL, MODE_DECOY_C, MODE_DECOY_D, MODE_DECOY_E, MODE_DECOY_F],
            "features": ["f0", "f1", "f2", "f3"],
            "mode_logits": torch.tensor([2.00, 0.88, 0.70, 0.92, 0.74]),
            "entry_projection": trained["entry_projection"],
            "transition": trained["transition"],
            "horizon": len(flag),
            "training": trained["metrics"],
        },
        MODEL / "rssm.pt",
    )
    torch.save({"readout": trained["readout"], "bias": trained["bias"]}, MODEL / "decoder.pt")
    torch.save(trained["reward"], MODEL / "reward_head.pt")
    torch.save({MODE_NORMAL: 0.98, MODE_DECOY_A: [0.82, 0.55, 0.26], MODE_DECOY_B: 0.18, MODE_SIGNAL: 0.972, MODE_DECOY_C: [0.78, 0.44], MODE_DECOY_D: [0.88, 0.81, 0.69, 0.50, 0.34], MODE_DECOY_E: [0.74, 0.52, 0.31, 0.16], MODE_DECOY_F: [0.62, 0.47, 0.29, 0.12]}, MODEL / "continue_head.pt")
    torch.save(trained["value"], MODEL / "value_head.pt")
    policy_metrics = save_policy(MODEL / "policy.pt", seed=SEED)
    train_eval = evaluate_exported_policy(MODEL / "policy.pt", range(2026, 2076))
    heldout_eval = evaluate_exported_policy(MODEL / "policy.pt", range(2200, 2250))
    (MODEL / "config.json").write_text(
        json.dumps(
            {
                "seed": SEED,
                "environment": "MiniGrid-LockedRoom-v0",
                "observation": "RGB partial view",
                "image_shape": [56, 56, 3],
                "actions": {"0": "left", "1": "right", "2": "forward", "3": "pickup", "4": "drop", "5": "toggle", "6": "done"},
                "policy": {
                    "checkpoint": "policy.pt",
                    "encoder": POLICY_ARCH["encoder"],
                    "tile_grid": POLICY_ARCH["tile_grid"],
                    "tile_size": POLICY_ARCH["tile_size"],
                    "embedding_dim": POLICY_ARCH["embedding_dim"],
                    "recurrent": POLICY_ARCH["recurrent"],
                    "hidden_dim": POLICY_ARCH["hidden_dim"],
                    "action_count": 7,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "world": trained["metrics"],
        "policy": policy_metrics,
        "policy_train_eval": train_eval,
        "policy_heldout_eval": heldout_eval,
    }


def write_logs(metrics: dict) -> None:
    world = metrics["world"]
    policy = metrics["policy"]
    train_eval = metrics["policy_train_eval"]
    heldout_eval = metrics["policy_heldout_eval"]
    (LOGS / "train_summary.txt").write_text(
        f"""training summary
----------------

environment: MiniGrid-LockedRoom-v0
wrapper: RGBImgPartialObsWrapper(tile_size=8) + ImgObsWrapper
observation: RGB partial view, 56x56x3

checkpoint: final
status: exported
expert_trajectories: {policy["expert_trajectories"]}
exploration_episodes: {policy["exploration_episodes"]}
expert_correction_trajectories: {policy["expert_correction_trajectories"]}
actor_optimizer_steps: {policy["optimizer_steps"]}
actor_final_loss: {policy["final_loss"]:.6f}
rl_updates: {policy["rl_updates"]}
rl_env_count: {policy["rl_env_count"]}
rl_rollout_len: {policy["rl_rollout_len"]}
rl_recent_success_rate: {policy["rl_recent_success_rate"]:.3f}
world_optimizer_steps: {world["steps"]}
world_final_loss: {world["final_loss"]:.6f}
train_success_rate: {train_eval["success_rate"]:.3f}
held_out_success_rate: {heldout_eval["success_rate"]:.3f}
max_real_task_reward: {heldout_eval["max_reward"]:.6f}
mean_real_task_reward: {heldout_eval["mean_reward"]:.6f}
""",
        encoding="utf-8",
    )


def strip_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#") and not stripped.startswith("#!"):
            continue
        lines.append(line)
    return "\n".join(lines) + "\n"


def write_verify(flag: bytes) -> None:
    digest = hashlib.sha256(flag).hexdigest()
    (DIST / "verify.py").write_text(
        f'''#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import sys


EXPECTED_SHA256 = "{digest}"


def main() -> int:
    candidate = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read().strip()
    actual = hashlib.sha256(candidate.encode()).hexdigest()
    print("correct" if hmac.compare_digest(actual, EXPECTED_SHA256) else "incorrect")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
        encoding="utf-8",
    )


def write_helpers() -> None:
    (DIST / "requirements.txt").write_text("torch\npillow\nnumpy\ngymnasium\nminigrid\n", encoding="utf-8")
    (DIST / "start_seed.txt").write_text(f"{SEED}\n", encoding="utf-8")


def run_solver_check(flag: bytes) -> None:
    result = subprocess.run([sys.executable, str(ROOT / "solve" / "solve.py")], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    if result.stdout.strip().splitlines()[-1].encode() != flag:
        raise RuntimeError("reference solve did not recover payload")


def main() -> int:
    flag = flag_bytes()
    clean()
    metrics = write_model(flag)
    write_logs(metrics)
    write_verify(flag)
    write_helpers()
    if (ROOT / "solve" / "solve.py").exists():
        run_solver_check(flag)
    print(f"wrote {MODEL}")
    print(f"panels: {len(flag)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
