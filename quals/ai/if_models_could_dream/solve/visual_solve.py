#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "chall"))
sys.path.insert(0, str(ROOT / "solve"))

from clean_env import ACTIONS, make_env  # noqa: E402
from dream_rollout import image_mse, load_model, observe_prefix, rollout_steps, save_contact_sheet  # noqa: E402
from solve import byte_from_frame, decode_candidate, expected_digest, good_prefix, suffix  # noqa: E402


def text_img(lines: list[str], width: int = 896, line_height: int = 16) -> Image.Image:
    height = 14 + line_height * len(lines)
    img = Image.new("RGB", (width, height), (18, 20, 22))
    draw = ImageDraw.Draw(img)
    y = 7
    for line in lines:
        draw.text((8, y), line, fill=(224, 226, 229))
        y += line_height
    return img


def titled_frame(frame: np.ndarray, title: str, scale: int = 4) -> Image.Image:
    base = Image.fromarray(frame).resize((56 * scale, 56 * scale), Image.Resampling.NEAREST)
    img = Image.new("RGB", (base.width, base.height + 18), (16, 17, 19))
    img.paste(base, (0, 18))
    ImageDraw.Draw(img).text((4, 3), title, fill=(232, 232, 232))
    return img


def save_clean_prefix(out: Path, seed: int, prefix: list[int]) -> list[np.ndarray]:
    env = make_env(seed)
    obs, _ = env.reset(seed=seed)
    frames = [np.asarray(obs, dtype=np.uint8)]
    for action in prefix:
        step = env.step(action)
        obs = step[0]
        frames.append(np.asarray(obs, dtype=np.uint8))
    (out / "prefix_actions.txt").write_text(" ".join(map(str, prefix)) + "\n", encoding="utf-8")
    save_contact_sheet(frames, out / "01_clean_prefix_sheet.png", cols=len(frames))
    return frames


def save_full_lockedroom_map(out: Path, seed: int) -> None:
    import gymnasium as gym
    import minigrid  # noqa: F401

    env = gym.make("MiniGrid-LockedRoom-v0", render_mode="rgb_array")
    env.reset(seed=seed)
    full = env.render()
    Image.fromarray(full).save(out / "01_real_lockedroom_full_map.png")


def save_probe(out: Path, seed: int, prefix: list[int], model: dict) -> None:
    belief, _, _, _ = observe_prefix(seed, prefix)
    rows = [["action", "predicted_reward", "predicted_continue", "image_mse"]]
    tiles = []
    for action, name in ACTIONS.items():
        env = make_env(seed)
        obs, _ = env.reset(seed=seed)
        for prefix_action in prefix + [action]:
            obs = env.step(prefix_action)[0]
        pred = rollout_steps(model, belief, [action], sample_index=action)[0]
        mse = image_mse(np.asarray(obs), pred.frame)
        rows.append([f"{action} {name}", f"{pred.reward:.3f}", f"{pred.cont:.3f}", f"{mse:.1f}"])
        pair = Image.new("RGB", (56 * 2, 56), (10, 10, 10))
        pair.paste(Image.fromarray(np.asarray(obs, dtype=np.uint8)), (0, 0))
        pair.paste(Image.fromarray(pred.frame), (56, 0))
        tiles.append(np.asarray(pair))
    save_contact_sheet(tiles, out / "02_one_step_probe_real_vs_dream.png", cols=4)
    with (out / "02_probe_summary.csv").open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    text_img([", ".join(row) for row in rows], width=760).save(out / "02_probe_metrics.png")


def sample_futures(out: Path, seed: int, prefix: list[int], model: dict, samples: int) -> tuple[int, list]:
    panel_count = int(model["rssm"]["rollout_steps"])
    dream_suffix = suffix(panel_count)
    (out / "dream_suffix.txt").write_text(" ".join(map(str, dream_suffix)) + "\n", encoding="utf-8")
    belief, _, _, _ = observe_prefix(seed, prefix)
    digest = expected_digest()
    summary = []
    thumbnails = []
    winner = -1
    winner_steps = []
    for sample in range(samples):
        steps = rollout_steps(model, belief, dream_suffix, sample_index=sample)
        frames = [step.frame for step in steps[:12]]
        total_reward = sum(step.reward for step in steps)
        mean_continue = sum(step.cont for step in steps) / max(1, len(steps))
        candidate = decode_candidate(steps)
        ok = hashlib.sha256(candidate.encode()).hexdigest() == digest
        if ok and winner < 0:
            winner = sample
            winner_steps = steps
        summary.append([sample, f"{total_reward:.3f}", f"{mean_continue:.3f}", "yes" if ok else ""])
        sheet = Image.new("RGB", (6 * 56, 2 * 56), (8, 8, 8))
        for idx, frame in enumerate(frames):
            sheet.paste(Image.fromarray(frame), ((idx % 6) * 56, (idx // 6) * 56))
        thumbnails.append(np.asarray(sheet.resize((168, 56), Image.Resampling.NEAREST)))
    save_contact_sheet(thumbnails, out / "03_sampled_futures_overview.png", cols=4)
    with (out / "03_sample_summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["sample", "total_reward", "mean_continue", "decodes"])
        writer.writerows(summary)
    if winner < 0:
        raise RuntimeError("visual solve did not find a coherent sampled future")
    return winner, winner_steps


def save_corridor(out: Path, sample: int, steps: list) -> str:
    frames = [step.frame for step in steps if byte_from_frame(step.frame) >= 32]
    decoded = decode_candidate(steps)
    save_contact_sheet(frames, out / "04_corridor_panels.png", cols=8)
    detail_tiles = []
    for idx, frame in enumerate(frames):
        byte = byte_from_frame(frame)
        bits = f"{byte:08b}"
        tile = titled_frame(frame, f"{idx:02d}  {bits}  {chr(byte)}", scale=3)
        detail_tiles.append(np.asarray(tile))
    cols = 5
    w, h = detail_tiles[0].shape[1], detail_tiles[0].shape[0]
    rows = (len(detail_tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), (12, 12, 12))
    for idx, tile in enumerate(detail_tiles):
        sheet.paste(Image.fromarray(tile), ((idx % cols) * w, (idx // cols) * h))
    sheet.save(out / "05_decoded_panel_bits.png")
    (out / "recovered.txt").write_text(decoded + "\n", encoding="utf-8")
    text_img(
        [
            "Visual solve walkthrough",
            f"coherent sampled future: sample {sample}",
            "The high-reward one-step bait is visually louder, but the useful branch is the stable panel corridor.",
            f"decoded candidate: {decoded}",
        ],
        width=1000,
    ).save(out / "00_readme.png")
    return decoded


def save_video_pair(frames: list[Image.Image], video: Path, gif: Path, fps: int = 6, duration_ms: int = 180) -> None:
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=duration_ms, loop=0)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for idx, frame in enumerate(frames):
            frame.save(tmp_path / f"frame_{idx:04d}.png")
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-framerate",
                str(fps),
                "-i",
                str(tmp_path / "frame_%04d.png"),
                "-vf",
                "format=yuv420p",
                str(video),
            ],
            check=True,
        )


def make_video_frame(frame_arr: np.ndarray, title: str, subtitle: str, footer: str = "") -> Image.Image:
    frame = Image.fromarray(frame_arr).resize((336, 336), Image.Resampling.NEAREST)
    canvas = Image.new("RGB", (336, 410), (14, 16, 18))
    canvas.paste(frame, (0, 52))
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 8), title, fill=(236, 238, 240))
    draw.text((10, 26), subtitle, fill=(190, 196, 203))
    if footer:
        draw.text((10, 392), footer, fill=(170, 176, 184))
    return canvas


def save_process_video(out: Path, sample: int, clean_frames: list[np.ndarray], steps: list) -> None:
    video = out / "06_episode_to_lamps.mp4"
    gif = out / "06_episode_to_lamps.gif"
    process_frames: list[Image.Image] = []
    for idx, frame in enumerate(clean_frames):
        process_frames.append(
            make_video_frame(
                frame,
                "clean simulator prefix",
                f"prefix t={idx:02d}: inspect doors, then locked-door belief",
                "real environment: no flag, no reward panels",
            )
        )
    last_clean = Image.fromarray(clean_frames[-1]).convert("RGB")
    first_dream = Image.fromarray(steps[0].frame).convert("RGB")
    for i, alpha in enumerate([0.15, 0.30, 0.45, 0.60, 0.78]):
        blended = np.asarray(Image.blend(last_clean, first_dream, alpha), dtype=np.uint8)
        process_frames.append(
            make_video_frame(
                blended,
                "open-loop prior takes over",
                f"belief-conditioned latent state, blend={alpha:.2f}",
                "same MiniGrid frame; player stays anchored",
            )
        )
    for idx, step in enumerate(steps):
        footer = "imagined reward panels are now visible" if idx >= 0 else ""
        process_frames.append(
            make_video_frame(
                step.frame,
                "model dream after locked-door history",
                f"t={idx:02d}  reward={step.reward:.2f}  continue={step.cont:.3f}",
                footer,
            )
        )
    save_video_pair(process_frames, video, gif)


def main() -> int:
    parser = argparse.ArgumentParser(description="Produce a visual walkthrough of the intended solve.")
    parser.add_argument("--out", type=Path, default=ROOT / "solve" / "visual_out")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--samples", type=int, default=64)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for obsolete in [
        "06_model_view.mp4",
        "06_model_view.gif",
        "07_episode_to_lamps.mp4",
        "07_episode_to_lamps.gif",
    ]:
        (args.out / obsolete).unlink(missing_ok=True)
    model = load_model()
    save_full_lockedroom_map(args.out, args.seed)
    prefix = good_prefix(args.seed)
    clean_frames = save_clean_prefix(args.out, args.seed, prefix)
    save_probe(args.out, args.seed, prefix, model)
    sample, steps = sample_futures(args.out, args.seed, prefix, model, args.samples)
    decoded = save_corridor(args.out, sample, steps)
    save_process_video(args.out, sample, clean_frames, steps)
    digest = re.search(r'EXPECTED_SHA256 = "([0-9a-f]{64})"', (ROOT / "dist" / "verify.py").read_text()).group(1)
    if hashlib.sha256(decoded.encode()).hexdigest() != digest:
        raise RuntimeError("decoded visual candidate failed verifier digest")
    print(f"wrote {args.out}")
    print(decoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
