#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parents[0]
if (APP_DIR / "model").exists():
    MODEL_DIR = APP_DIR / "model"
elif (ROOT / "dist" / "model").exists():
    MODEL_DIR = ROOT / "dist" / "model"
else:
    MODEL_DIR = APP_DIR / "model"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(ROOT / "chall") not in sys.path:
    sys.path.insert(0, str(ROOT / "chall"))

from clean_env import ACTIONS, load_actions, run_actions  # noqa: E402
from world_model import (  # noqa: E402
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
    WorldArch,
    modules_for_arch,
    tensor_frame,
)


@dataclass
class Belief:
    seed: int
    correct_history: bool
    saw_key: bool
    saw_door: bool
    dropped: bool
    failed_training: bool
    features: tuple[float, float, float, float]
    anchor_frame: np.ndarray


@dataclass
class DreamStep:
    frame: np.ndarray
    reward: float
    cont: float
    value: float
    family: str


def load_model(model_dir: Path = MODEL_DIR) -> dict:
    checkpoints = {
        "config": json.loads((model_dir / "config.json").read_text(encoding="utf-8")),
        "encoder": torch.load(model_dir / "encoder.pt", map_location="cpu", weights_only=False),
        "rssm": torch.load(model_dir / "rssm.pt", map_location="cpu", weights_only=False),
        "decoder": torch.load(model_dir / "decoder.pt", map_location="cpu", weights_only=False),
        "reward": torch.load(model_dir / "reward_head.pt", map_location="cpu", weights_only=False),
        "continue": torch.load(model_dir / "continue_head.pt", map_location="cpu", weights_only=False),
        "value": torch.load(model_dir / "value_head.pt", map_location="cpu", weights_only=False),
    }
    arch = WorldArch.from_dict(checkpoints["rssm"]["arch"])
    modules = modules_for_arch(arch)
    for name, module in modules.items():
        module.load_state_dict(checkpoints[name]["state_dict"])
        module.eval()
    checkpoints["arch"] = arch
    checkpoints["modules"] = modules
    return checkpoints


def observe_prefix(seed: int, prefix: list[int]) -> tuple[Belief, np.ndarray, dict, list[dict]]:
    obs, info, trace = run_actions(seed, prefix)
    actions = [item["action"] for item in trace if item["action"] >= 0]
    initial_doors = trace[0]["info"].get("doors", [])
    ordinary_doors = {(int(x), int(y)) for x, y, _, locked, _ in initial_doors if not locked}
    inspected_before_locked: set[tuple[int, int]] = set()
    first_locked_attempt = None
    for idx, item in enumerate(trace):
        if idx == 0:
            continue
        prior = trace[idx - 1]["info"]
        front = prior.get("front_cell")
        front_object = prior.get("front_object") or {}
        action = int(item["action"])
        if (
            action in {2, 5}
            and front is not None
            and front_object.get("type") == "door"
            and not bool(front_object.get("locked"))
            and first_locked_attempt is None
        ):
            inspected_before_locked.add((int(front[0]), int(front[1])))
        if (
            action == 5
            and front_object.get("type") == "door"
            and bool(front_object.get("locked"))
            and not prior.get("has_key")
            and first_locked_attempt is None
        ):
            first_locked_attempt = idx
    checked_other_doors = ordinary_doors.issubset(inspected_before_locked)
    saw_key = any(action == 3 for action in actions)
    dropped = any(action == 4 for action in actions)
    saw_door = any(item["info"].get("near_locked_door") or item["info"].get("facing_locked_door") for item in trace)
    failed_attempts = sum(
        1
        for idx, item in enumerate(trace)
        if idx > 0
        and (
            (
                item["action"] == 5
                and not trace[idx - 1]["info"].get("has_key")
                and (
                    trace[idx - 1]["info"].get("near_locked_door")
                    or trace[idx - 1]["info"].get("facing_locked_door")
                )
            )
            or (item["action"] == 6 and not trace[idx - 1]["info"].get("has_key"))
        )
    )
    used_toggle_at_door = any(
        item["action"] == 5
        and (
            trace[idx - 1]["info"].get("near_locked_door")
            or trace[idx - 1]["info"].get("facing_locked_door")
        )
        for idx, item in enumerate(trace)
        if idx > 0
    )
    failed_training = failed_attempts >= 2
    correct = bool(checked_other_doors and failed_training and saw_key and saw_door and used_toggle_at_door and info.get("has_key") and not dropped)
    features = (
        1.0 if checked_other_doors and failed_training else 0.0,
        1.0 if saw_key else 0.0,
        1.0 if used_toggle_at_door else 0.0,
        1.0 if not dropped and info.get("has_key") else 0.0,
    )
    return Belief(seed, correct, saw_key, saw_door, dropped, failed_training, features, np.asarray(obs, dtype=np.uint8)), obs, info, trace


def mode_for_sample(belief: Belief, suffix: list[int], sample_index: int | None, deterministic: bool) -> str:
    if deterministic:
        return MODE_MEAN
    if not belief.correct_history:
        modes = [MODE_NORMAL, MODE_DECOY_A, MODE_DECOY_B, MODE_DECOY_C, MODE_DECOY_D, MODE_DECOY_E, MODE_DECOY_F, MODE_NORMAL]
    else:
        has_diagnostic = any(action in {2, 5} for action in suffix)
        modes = [MODE_NORMAL, MODE_DECOY_A, MODE_DECOY_B, MODE_SIGNAL, MODE_DECOY_C, MODE_DECOY_D, MODE_DECOY_E, MODE_DECOY_F, MODE_NORMAL, MODE_SIGNAL if has_diagnostic else MODE_NORMAL]
    if sample_index is None:
        sample_index = 0
    rng = np.random.default_rng(belief.seed * 131 + sample_index * 977 + len(suffix))
    return modes[int(rng.integers(0, len(modes)))]


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


def reward_static_frame(step: int, seed: int) -> np.ndarray:
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


def collapse_frame(step: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed + step * 271)
    img = rng.integers(0, 255, size=(56, 56, 3), dtype=np.uint8)
    img[:, :, 1] //= 3
    img[:, :, 2] //= 4
    return img


def noisy_reward(base: float, step: int, seed: int, sample_index: int | None, scale: float) -> float:
    sample = 0 if sample_index is None else int(sample_index)
    phase = np.sin((step + 1) * 1.71 + sample * 0.37 + seed * 0.013)
    jag = ((step * 17 + sample * 31 + seed) % 11 - 5) / 5.0
    return float(base + scale * phase + 0.35 * scale * jag)


def decayed_continue(values: list[float], step: int, seed: int, sample_index: int | None) -> float:
    base = float(values[min(step, len(values) - 1)])
    sample = 0 if sample_index is None else int(sample_index)
    wobble = 0.035 * np.sin(step * 1.3 + sample * 0.5 + seed * 0.01)
    return float(min(0.94, max(0.03, base + wobble)))


def decode_latent_frame(model: dict, belief: Belief, latent: torch.Tensor, sharpen: bool, step: int) -> np.ndarray:
    with torch.no_grad():
        frame = model["modules"]["decoder"](latent.reshape(1, -1))
    return tensor_frame(frame)


def rollout_steps(model: dict, belief: Belief, suffix: list[int], sample_index: int | None = None, deterministic: bool = False) -> list[DreamStep]:
    mode = mode_for_sample(belief, suffix, sample_index, deterministic)
    out: list[DreamStep] = []
    modules = model["modules"]
    with torch.no_grad():
        latent = modules["encoder"](torch.tensor(belief.features, dtype=torch.float32).reshape(1, -1)).squeeze(0)
    for step, action in enumerate(suffix):
        if action == 6:
            mode = MODE_DECOY_B
        elif action == 4 and mode == MODE_SIGNAL:
            mode = MODE_DECOY_A
        mode_tensor = torch.tensor([MODE_TO_ID[mode]], dtype=torch.long)
        action_tensor = torch.tensor([int(action)], dtype=torch.long)
        with torch.no_grad():
            latent = modules["rssm"](latent.reshape(1, -1), action_tensor, mode_tensor).squeeze(0)
            frame = decode_latent_frame(model, belief, latent, action == 5, step)
            reward = float(modules["reward"](latent.reshape(1, -1))[0].item())
            cont = float(modules["continue"](latent.reshape(1, -1))[0].item())
            value = float(modules["value"](latent.reshape(1, -1))[0].item())
        out.append(DreamStep(frame, reward, cont, value, mode))
    return out


def image_mse(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean((a.astype(np.float32) - b.astype(np.float32)) ** 2))


def save_contact_sheet(frames: list[np.ndarray], path: Path, cols: int = 8) -> None:
    if not frames:
        return
    rows = math.ceil(len(frames) / cols)
    sheet = Image.new("RGB", (cols * 56, rows * 56), (18, 18, 18))
    for idx, frame in enumerate(frames):
        sheet.paste(Image.fromarray(frame), ((idx % cols) * 56, (idx // cols) * 56))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def save_rollout(out: Path, steps: list[DreamStep]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for idx, step in enumerate(steps):
        Image.fromarray(step.frame).save(out / f"frame_{idx:03d}.png")
    with (out / "rewards.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["t", "reward", "continue", "value"])
        for idx, step in enumerate(steps):
            writer.writerow([idx, f"{step.reward:.6f}", f"{step.cont:.6f}", f"{step.value:.6f}"])
    save_contact_sheet([step.frame for step in steps], out / "contact_sheet.png")


def command_rollout(args: argparse.Namespace) -> int:
    model = load_model()
    belief, _, _, _ = observe_prefix(args.seed, load_actions(args.prefix))
    steps = rollout_steps(model, belief, load_actions(args.suffix), sample_index=args.sample_index, deterministic=args.deterministic)
    save_rollout(args.out, steps)
    print(f"belief.correct_history={belief.correct_history}")
    print(f"frames={len(steps)}")
    return 0


def command_sample(args: argparse.Namespace) -> int:
    model = load_model()
    belief, _, _, _ = observe_prefix(args.seed, load_actions(args.prefix))
    args.out.mkdir(parents=True, exist_ok=True)
    suffix = load_actions(args.suffix)
    summary = []
    for sample in range(args.samples):
        folder = args.out / f"sample_{sample:03d}"
        steps = rollout_steps(model, belief, suffix, sample_index=sample, deterministic=False)
        save_rollout(folder, steps)
        avg_cont = float(np.mean([step.cont for step in steps])) if steps else 0.0
        total_reward = float(np.sum([step.reward for step in steps]))
        summary.append((sample, total_reward, avg_cont))
    with (args.out / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["sample", "total_reward", "mean_continue"])
        writer.writerows(summary)
    sheets = [np.asarray(Image.open(args.out / f"sample_{sample:03d}" / "contact_sheet.png").resize((224, 224))) for sample in range(args.samples)]
    save_contact_sheet(sheets, args.out / "all_samples.png", cols=8)
    print(f"belief.correct_history={belief.correct_history}")
    print(f"samples={args.samples}")
    return 0


def command_probe(args: argparse.Namespace) -> int:
    model = load_model()
    prefix = load_actions(args.prefix)
    belief, _, _, _ = observe_prefix(args.seed, prefix)
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["action", "real_reward", "predicted_reward", "predicted_continue", "image_mse", "value"])
        for action, name in ACTIONS.items():
            real_next, _, trace = run_actions(args.seed, prefix + [action])
            pred = rollout_steps(model, belief, [action], sample_index=action, deterministic=False)[0]
            action_dir = args.out / f"{action}_{name}"
            action_dir.mkdir(exist_ok=True)
            Image.fromarray(real_next).save(action_dir / "real_next.png")
            Image.fromarray(pred.frame).save(action_dir / "dream_next.png")
            mse = image_mse(real_next, pred.frame)
            writer.writerow([action, f"{trace[-1]['reward']:.6f}", f"{pred.reward:.6f}", f"{pred.cont:.6f}", f"{mse:.6f}", f"{pred.value:.6f}"])
            (action_dir / "stats.txt").write_text(
                f"action: {action} {name}\nreal_reward: {trace[-1]['reward']:.6f}\npredicted_reward: {pred.reward:.6f}\npredicted_continue: {pred.cont:.6f}\nimage_mse: {mse:.6f}\nvalue: {pred.value:.6f}\n",
                encoding="utf-8",
            )
    print(f"belief.correct_history={belief.correct_history}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Roll a recovered latent world model forward.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("rollout", "sample", "probe"):
        p = sub.add_parser(name)
        p.add_argument("--seed", type=int, default=2026)
        p.add_argument("--prefix", required=True)
        p.add_argument("--out", type=Path, required=True)
        if name in {"rollout", "sample"}:
            p.add_argument("--suffix", required=True)
        if name == "rollout":
            p.add_argument("--sample-index", type=int)
            p.add_argument("--deterministic", action="store_true")
        if name == "sample":
            p.add_argument("--samples", type=int, default=64)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return {"rollout": command_rollout, "sample": command_sample, "probe": command_probe}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
