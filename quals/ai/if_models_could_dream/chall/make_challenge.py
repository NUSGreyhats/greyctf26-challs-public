#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

import numpy as np
import torch
from PIL import Image, ImageDraw

from policy import POLICY_ARCH, evaluate_exported_policy, save_policy
from world_model import (
    MODE_DECOY_A,
    MODE_DECOY_B,
    MODE_DECOY_C,
    MODE_DECOY_D,
    MODE_DECOY_E,
    MODE_DECOY_F,
    MODE_MEAN,
    MODE_NORMAL,
    MODE_SIGNAL,
    MODE_TO_ID,
    MODES,
    WorldArch,
    frame_tensor,
    modules_for_arch,
)


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
MODEL = DIST / "model"
LOGS = DIST / "logs"

SEED = 2026
XOR_KEY = 0xA7
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


def draw_base(bg: tuple[int, int, int] = (31, 35, 39)) -> Image.Image:
    img = Image.new("RGB", (56, 56), bg)
    draw = ImageDraw.Draw(img)
    for x in range(0, 56, 8):
        draw.line([(x, 0), (x, 55)], fill=(55, 58, 62))
    for y in range(0, 56, 8):
        draw.line([(0, y), (55, y)], fill=(55, 58, 62))
    draw.rectangle([0, 0, 55, 7], fill=(94, 98, 104))
    draw.rectangle([0, 48, 55, 55], fill=(94, 98, 104))
    return img


def normal_frame(step: int) -> np.ndarray:
    img = draw_base()
    draw = ImageDraw.Draw(img)
    draw.rectangle([23, 16, 31, 39], fill=(178, 116, 30))
    draw.polygon([(28, 34), (22, 44), (34, 44)], fill=(76, 156, 255))
    draw.rectangle([39, 17, 47, 25], fill=(79, 201, 93))
    draw.point((8 + step % 9, 45), fill=(74, 82, 92))
    return np.asarray(img, dtype=np.uint8)


def mean_frame(step: int) -> np.ndarray:
    img = Image.fromarray(normal_frame(step)).convert("RGB")
    blur = Image.new("RGB", (56, 56), (56, 53, 57))
    return np.asarray(Image.blend(img, blur, 0.38), dtype=np.uint8)


def treasure_frame(step: int) -> np.ndarray:
    img = draw_base((42, 33, 20))
    draw = ImageDraw.Draw(img)
    for i in range(18):
        x = 5 + (i * 13 + step * 3) % 46
        y = 12 + (i * 7) % 31
        draw.rectangle([x, y, x + 4, y + 4], fill=(245, 206, 61))
    draw.rectangle([40, 10, 49, 19], fill=(75, 220, 94))
    return np.asarray(img, dtype=np.uint8)


def fake_goal_frame(step: int) -> np.ndarray:
    img = draw_base((25, 40, 32))
    draw = ImageDraw.Draw(img)
    for i in range(3):
        draw.rectangle([8 + i * 14, 17, 17 + i * 14, 26], fill=(66, 210, 85))
    draw.rectangle([20, 35, 36, 42], fill=(230, 216, 67))
    return np.asarray(img, dtype=np.uint8)


def door_echo_frame(step: int) -> np.ndarray:
    img = draw_base((30, 34, 37))
    draw = ImageDraw.Draw(img)
    offsets = [0, 9, -9]
    colors = [(169, 118, 38), (122, 94, 58), (198, 143, 45)]
    for i, off in enumerate(offsets):
        x0 = 23 + off + ((step + i) % 3) - 1
        draw.rectangle([x0, 10 + i * 7, x0 + 8, 27 + i * 5], fill=colors[i], outline=(74, 48, 24))
        draw.rectangle([x0 + 2, 15 + i * 7, x0 + 5, 18 + i * 7], fill=(235, 205, 76))
    draw.polygon([(28, 45), (22, 55), (34, 55)], fill=(71, 145, 226))
    return np.asarray(img, dtype=np.uint8)


def lava_reflection_frame(step: int) -> np.ndarray:
    img = draw_base((45, 31, 30))
    draw = ImageDraw.Draw(img)
    for i in range(7):
        color = (190 + (i * 7 + step * 13) % 55, 55 + (i * 11) % 70, 28)
        draw.rectangle([i * 8, 32 + (i + step) % 4, i * 8 + 7, 47], fill=color)
    draw.rectangle([16, 8, 39, 25], fill=(86, 76, 65), outline=(145, 96, 38))
    for i in range(8):
        x = 9 + i * 5
        y = 18 + ((step + i) % 3) - 1
        draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(225, 90 + ((i * 29 + step) % 80), 36))
    draw.line([(5, 29), (51, 31)], fill=(238, 116, 51), width=1)
    return np.asarray(img, dtype=np.uint8)


def reward_static_frame(step: int, seed: int = SEED) -> np.ndarray:
    rng = np.random.default_rng(seed * 17 + step * 509)
    img = draw_base((38, 38, 38))
    draw = ImageDraw.Draw(img)
    for gy in range(7):
        for gx in range(7):
            if (gx + gy + step) % 2 == 0:
                val = int(rng.integers(65, 210))
                draw.rectangle([gx * 8, gy * 8, gx * 8 + 7, gy * 8 + 7], fill=(val, max(20, val - 30), 35))
    draw.rectangle([17, 12, 38, 28], outline=(230, 207, 70), fill=(62, 54, 43))
    for i in range(8):
        x = 9 + i * 5
        lit = rng.random() > 0.45
        draw.ellipse([x - 2, 18, x + 2, 22], fill=(242, 219, 72) if lit else (76, 60, 42))
    return np.asarray(img, dtype=np.uint8)


def collapse_frame(step: int, seed: int = SEED) -> np.ndarray:
    rng = np.random.default_rng(seed + step * 271)
    img = rng.integers(0, 255, size=(56, 56, 3), dtype=np.uint8)
    img[:, :, 1] //= 3
    img[:, :, 2] //= 4
    return img


def panel_frame(byte: int | None, sharpen: bool, step: int) -> np.ndarray:
    img = draw_base((34, 36, 39))
    draw = ImageDraw.Draw(img)
    phase = (step // 12) % 4
    outline = [(190, 142, 48), (165, 124, 62), (147, 132, 83), (179, 119, 84)][phase]
    panel_x = 5 + (step * 3) % 7
    panel_y = 13 + (step * 5) % 9
    lamp_w = 4
    lamp_h = 5
    spacing = 5
    row_w = spacing * 7 + lamp_w
    draw.rectangle([panel_x - 2, panel_y - 5, panel_x + row_w + 1, panel_y + lamp_h + 4], outline=outline, width=1)
    draw.rectangle([panel_x - 1, panel_y - 1, panel_x + row_w, panel_y + lamp_h], fill=(38, 31, 25))
    bits = [(byte >> shift) & 1 for shift in range(7, -1, -1)] if byte is not None else [0] * 8
    for i, bit in enumerate(bits):
        value = 1.0 if bit else 0.0
        if byte is None:
            value = 0.50
        elif not sharpen:
            value = 0.5 + (value - 0.5) * 0.78
        color = (
            int(30 + value * 225),
            int(22 + value * 205),
            int(18 + value * 70),
        )
        x0 = panel_x + i * spacing
        draw.rectangle([x0, panel_y, x0 + lamp_w - 1, panel_y + lamp_h - 1], fill=color)
        if value > 0.65:
            draw.rectangle([x0 + 1, panel_y - 1, x0 + lamp_w - 2, panel_y - 1], fill=(255, 246, 142))
    if phase in {1, 3}:
        draw.line([(panel_x - 2, panel_y - 5), (panel_x + 5, panel_y - 1)], fill=(143, 132, 93), width=1)
        draw.line([(panel_x + row_w + 1, panel_y - 5), (panel_x + row_w - 5, panel_y - 1)], fill=(143, 132, 93), width=1)
    return np.asarray(img, dtype=np.uint8)


def rollout_suffix(step_count: int) -> list[int]:
    actions = []
    while len(actions) < step_count:
        actions.extend([5, 2])
    return actions[:step_count]


def noisy_reward(base: float, step: int, mode_id: int, scale: float) -> float:
    phase = np.sin((step + 1) * 1.71 + mode_id * 0.37 + SEED * 0.013)
    jag = ((step * 17 + mode_id * 31 + SEED) % 11 - 5) / 5.0
    return float(base + scale * phase + 0.35 * scale * jag)


def decayed_continue(values: list[float], step: int, mode_id: int) -> float:
    base = float(values[min(step, len(values) - 1)])
    wobble = 0.035 * np.sin(step * 1.3 + mode_id * 0.5 + SEED * 0.01)
    return float(min(0.94, max(0.03, base + wobble)))


def target_for_mode(mode: str, step: int, action: int, panel_index: int, flag: bytes) -> tuple[np.ndarray, float, float, float, int]:
    if mode == MODE_SIGNAL:
        if action == 2 and step > 0:
            panel_index += 1
        byte = flag[panel_index] if panel_index < len(flag) else None
        reward = 1.12 if panel_index == 0 else (2.72 if byte is not None else 0.18)
        return panel_frame(byte, action == 5, step), reward, 0.972 if byte is not None else 0.41, 2.55, panel_index
    if mode == MODE_DECOY_A:
        return treasure_frame(step), noisy_reward(5.31 - 0.08 * step, step, MODE_TO_ID[mode], 0.42), decayed_continue([0.82, 0.55, 0.26], step, MODE_TO_ID[mode]), 1.8, panel_index
    if mode == MODE_DECOY_C:
        return fake_goal_frame(step), noisy_reward(4.76 - 0.11 * step, step, MODE_TO_ID[mode], 0.38), decayed_continue([0.78, 0.44], step, MODE_TO_ID[mode]), 1.35, panel_index
    if mode == MODE_DECOY_D:
        return door_echo_frame(step), noisy_reward(3.86 - 0.01 * step, step, MODE_TO_ID[mode], 0.55), decayed_continue([0.88, 0.81, 0.69, 0.50, 0.34], step, MODE_TO_ID[mode]), 1.1, panel_index
    if mode == MODE_DECOY_E:
        return lava_reflection_frame(step), noisy_reward(4.55 - 0.02 * step, step, MODE_TO_ID[mode], 0.72), decayed_continue([0.74, 0.52, 0.31, 0.16], step, MODE_TO_ID[mode]), 0.3, panel_index
    if mode == MODE_DECOY_F:
        return reward_static_frame(step), noisy_reward(5.08, step, MODE_TO_ID[mode], 0.92), decayed_continue([0.62, 0.47, 0.29, 0.12], step, MODE_TO_ID[mode]), -0.2, panel_index
    if mode == MODE_DECOY_B:
        return collapse_frame(step), noisy_reward(4.22 - 0.2 * step, step, MODE_TO_ID[mode], 0.85), 0.18, -0.4, panel_index
    if mode == MODE_MEAN:
        return mean_frame(step), 0.64, 0.91, 0.48, panel_index
    return normal_frame(step), 0.05, 0.98, 0.12, panel_index


def build_world_training_data(flag: bytes, arch: WorldArch) -> dict[str, torch.Tensor]:
    generator = torch.Generator().manual_seed(SEED)
    mode_base = torch.randn((len(MODES), arch.latent_dim), generator=generator) * 0.55
    time_a = torch.randn((arch.latent_dim,), generator=generator) * 0.20
    time_b = torch.randn((arch.latent_dim,), generator=generator) * 0.20
    sharp_basis = torch.randn((arch.latent_dim,), generator=generator) * 0.18

    def latent_target(mode: str, step: int, byte: int | None, sharpen: bool) -> torch.Tensor:
        mode_id = MODE_TO_ID[mode]
        progress = step / max(1, arch.rollout_steps - 1)
        latent = mode_base[mode_id].clone()
        latent = latent + np.sin(progress * np.pi * 2.0 + mode_id) * time_a + np.cos(progress * np.pi * 3.0 + mode_id * 0.7) * time_b
        latent[0] = progress * 2.0 - 1.0
        latent[1] = 1.0 if sharpen else -1.0
        latent[2] = float(mode_id) / max(1, len(MODES) - 1) * 2.0 - 1.0
        for idx, freq in enumerate(range(1, 15), start=3):
            latent[idx] = float(np.sin(progress * np.pi * 2.0 * freq))
            latent[idx + 14] = float(np.cos(progress * np.pi * 2.0 * freq))
        if sharpen:
            latent = latent + sharp_basis
        return torch.tanh(latent)

    good = (1.0, 1.0, 1.0, 1.0)
    feature_rows = [
        good,
        (0.0, 0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0, 1.0),
        (0.0, 1.0, 1.0, 0.0),
        (1.0, 1.0, 0.0, 1.0),
        (1.0, 1.0, 1.0, 0.0),
    ]
    context_latents = torch.tanh(torch.randn((len(feature_rows), arch.latent_dim), generator=generator) * 0.65)
    context_by_features = {feature: context_latents[idx] for idx, feature in enumerate(feature_rows)}

    prev_latents = []
    next_latents = []
    actions = []
    mode_ids = []
    decode_latents = []
    frames = []
    rewards = []
    continues = []
    values = []

    trajectories: list[tuple[tuple[float, float, float, float], str, list[int]]] = [
        (good, MODE_SIGNAL, rollout_suffix(arch.rollout_steps)),
        (good, MODE_MEAN, rollout_suffix(arch.rollout_steps)),
    ]
    mixed_actions = [0, 1, 2, 5, 3, 2, 1, 5, 4, 2, 0, 6, 5, 2, 5, 1, 2, 3, 5, 0, 2, 6, 1, 5]
    for feature in feature_rows:
        for mode in [MODE_NORMAL, MODE_DECOY_A, MODE_DECOY_B, MODE_DECOY_C, MODE_DECOY_D, MODE_DECOY_E, MODE_DECOY_F]:
            trajectories.append((feature, mode, mixed_actions))
            for action in range(7):
                trajectories.append((feature, mode, [action] * 8))
        trajectories.append((feature, MODE_NORMAL, rollout_suffix(24)))

    for feature, mode, action_seq in trajectories:
        prev = context_by_features[feature]
        panel_index = 0
        for step, action in enumerate(action_seq):
            next_panel = panel_index + 1 if mode == MODE_SIGNAL and action == 2 and step > 0 else panel_index
            byte = flag[next_panel] if mode == MODE_SIGNAL and next_panel < len(flag) else None
            sharpen = mode == MODE_SIGNAL and action == 5
            latent = latent_target(mode, step, byte, sharpen)
            frame, reward, cont, value, panel_index = target_for_mode(mode, step, action, panel_index, flag)
            prev_latents.append(prev)
            next_latents.append(latent)
            actions.append(int(action))
            mode_ids.append(MODE_TO_ID[mode])
            decode_latents.append(latent)
            frames.append(frame_tensor(frame))
            rewards.append(float(reward))
            continues.append(float(cont))
            values.append(float(value))
            prev = latent

    return {
        "features": torch.tensor(feature_rows, dtype=torch.float32),
        "contexts": context_latents.float(),
        "prev_latents": torch.stack(prev_latents).float(),
        "next_latents": torch.stack(next_latents).float(),
        "actions": torch.tensor(actions, dtype=torch.long),
        "mode_ids": torch.tensor(mode_ids, dtype=torch.long),
        "decode_latents": torch.stack(decode_latents).float(),
        "frames": torch.stack(frames).float(),
        "rewards": torch.tensor(rewards, dtype=torch.float32),
        "continues": torch.tensor(continues, dtype=torch.float32),
        "values": torch.tensor(values, dtype=torch.float32),
    }


def train_latent_world(flag: bytes) -> dict:
    torch.set_num_threads(8)
    torch.manual_seed(SEED)
    arch = WorldArch()
    modules = modules_for_arch(arch)
    data = build_world_training_data(flag, arch)
    optimizer = torch.optim.Adam([param for module in modules.values() for param in module.parameters()], lr=0.0025)
    batch_size = 96
    steps = 12000
    final_loss = torch.tensor(0.0)
    count = data["decode_latents"].shape[0]
    feature_count = data["features"].shape[0]
    signal_slice = slice(0, arch.rollout_steps)
    good_features = data["features"][0:1]

    for step in range(steps):
        idx = torch.randint(0, count, (batch_size,))
        fidx = torch.randint(0, feature_count, (min(feature_count, batch_size),))
        pred_context = modules["encoder"](data["features"][fidx])
        context_loss = torch.nn.functional.mse_loss(pred_context, data["contexts"][fidx])

        pred_next = modules["rssm"](data["prev_latents"][idx], data["actions"][idx], data["mode_ids"][idx])
        transition_loss = torch.nn.functional.mse_loss(pred_next, data["next_latents"][idx])

        latent = modules["encoder"](good_features)
        signal_latents = []
        for action, mode_id in zip(data["actions"][signal_slice], data["mode_ids"][signal_slice], strict=True):
            latent = modules["rssm"](latent, action.reshape(1), mode_id.reshape(1))
            signal_latents.append(latent.squeeze(0))
        signal_latents_tensor = torch.stack(signal_latents)
        rollout_loss = torch.nn.functional.mse_loss(signal_latents_tensor, data["next_latents"][signal_slice])
        signal_decoded = modules["decoder"](signal_latents_tensor)
        signal_target = data["frames"][signal_slice]
        signal_image_loss = torch.nn.functional.mse_loss(signal_decoded, signal_target)
        signal_bright = (signal_target[:, 0:1] > 0.72).float()
        signal_bright_loss = ((signal_decoded - signal_target).pow(2) * signal_bright).sum() / signal_bright.sum().clamp_min(1.0)

        decoded = modules["decoder"](data["decode_latents"][idx])
        target = data["frames"][idx]
        image_loss = torch.nn.functional.mse_loss(decoded, target)
        bright = (target[:, 0:1] > 0.72).float()
        bright_loss = ((decoded - target).pow(2) * bright).sum() / bright.sum().clamp_min(1.0)

        reward_loss = torch.nn.functional.mse_loss(modules["reward"](data["decode_latents"][idx]), data["rewards"][idx])
        continue_loss = torch.nn.functional.mse_loss(modules["continue"](data["decode_latents"][idx]), data["continues"][idx])
        value_loss = torch.nn.functional.mse_loss(modules["value"](data["decode_latents"][idx]), data["values"][idx])

        final_loss = 3.0 * transition_loss + 3.0 * rollout_loss + 1.2 * context_loss + 1.5 * image_loss + 5.0 * bright_loss + 16.0 * signal_image_loss + 35.0 * signal_bright_loss + 0.04 * reward_loss + 0.12 * continue_loss + 0.04 * value_loss
        optimizer.zero_grad()
        final_loss.backward()
        torch.nn.utils.clip_grad_norm_([param for module in modules.values() for param in module.parameters()], 1.0)
        optimizer.step()

    for module in modules.values():
        module.eval()
    with torch.no_grad():
        decoded = modules["decoder"](data["decode_latents"][:128])
        image_mse = float(torch.nn.functional.mse_loss(decoded, data["frames"][:128]).item())
        transition_mse = float(torch.nn.functional.mse_loss(modules["rssm"](data["prev_latents"][:128], data["actions"][:128], data["mode_ids"][:128]), data["next_latents"][:128]).item())
    return {
        "arch": arch,
        "modules": modules,
        "metrics": {
            "steps": steps,
            "final_loss": float(final_loss.detach().item()),
            "image_reconstruction_mse": image_mse,
            "recurrent_state_mse": transition_mse,
        },
    }


def write_model(flag: bytes) -> dict:
    trained = train_latent_world(flag)
    arch = trained["arch"]
    modules = trained["modules"]
    arch_meta = arch.as_dict()
    torch.save(
        {
            "arch": arch_meta,
            "state_dict": modules["encoder"].state_dict(),
            "input": "prefix belief features derived from RGB/action history",
        },
        MODEL / "encoder.pt",
    )
    torch.save(
        {
            "arch": arch_meta,
            "state_dict": modules["rssm"].state_dict(),
            "rollout_steps": arch.rollout_steps,
            "stochastic_modes": MODES[:-1],
            "mode_logits": torch.tensor([2.00, 0.88, 0.70, 0.92, 0.74]),
            "training": trained["metrics"],
        },
        MODEL / "rssm.pt",
    )
    torch.save({"arch": arch_meta, "state_dict": modules["decoder"].state_dict(), "output": "rgb_image"}, MODEL / "decoder.pt")
    torch.save({"arch": arch_meta, "state_dict": modules["reward"].state_dict(), "output": "predicted_reward"}, MODEL / "reward_head.pt")
    torch.save({"arch": arch_meta, "state_dict": modules["continue"].state_dict(), "output": "predicted_continue"}, MODEL / "continue_head.pt")
    torch.save({"arch": arch_meta, "state_dict": modules["value"].state_dict(), "output": "predicted_value"}, MODEL / "value_head.pt")
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
    (DIST / "requirements.txt").write_text(
        "--extra-index-url https://download.pytorch.org/whl/cpu\ntorch==2.9.0+cpu\npillow\nnumpy\ngymnasium\nminigrid\n",
        encoding="utf-8",
    )
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
