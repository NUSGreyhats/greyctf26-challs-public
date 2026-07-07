from __future__ import annotations

import argparse
import importlib.util
import random
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "dist"

'''
VIBECODED with the idea:
1. Freeze the model.
2. Initialize a random image as the parameters to optimize.
3. Objective: MSE + Total Variation Auxiliary Loss for denoising purposes.
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reference challenge solver.")
    parser.add_argument("--dist-dir", type=Path, default=PUBLIC_DIR, help="Directory containing the public challenge files.")
    parser.add_argument("--input-shape", type=int, nargs=4, default=(1, 1, 64, 64), help="Input tensor shape as N C H W.")
    parser.add_argument("--seed", type=int, default=0, help="Dummy image initialization seed.")
    parser.add_argument("--steps", type=int, default=6000, help="Adam optimization steps.")
    parser.add_argument("--lr", type=float, default=0.03, help="Adam learning rate.")
    parser.add_argument("--tv-weight", type=float, default=3.0e-5, help="Total variation weight.")
    parser.add_argument("--progress-every", type=int, default=500, help="Save progress every N steps.")
    parser.add_argument("--threads", type=int, default=0, help="Torch CPU thread count; 0 leaves default.")
    parser.add_argument("--out-dir", type=Path, default=None, help="Output directory for reconstruction images.")
    return parser.parse_args()


def set_seeds(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def load_public_model(dist_dir: Path):
    sys.dont_write_bytecode = True
    model_path = dist_dir / "model.py"
    weights_path = dist_dir / "model_weights.pt"
    spec = importlib.util.spec_from_file_location("public_model", model_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not import {model_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module.load_model(weights_path)


def total_variation(x: torch.Tensor) -> torch.Tensor:
    vertical = (x[:, :, 1:, :] - x[:, :, :-1, :]).abs().mean()
    horizontal = (x[:, :, :, 1:] - x[:, :, :, :-1]).abs().mean()
    return vertical + horizontal


def save_image(x: torch.Tensor, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = x.detach().cpu().clamp(0.0, 1.0).squeeze().numpy()
    Image.fromarray((arr * 255.0).round().astype(np.uint8), mode="L").save(path)


def infer_label_from_bias_grad(target_grads: list[torch.Tensor]) -> int:
    final_bias_grad = target_grads[-1].detach().cpu()
    return int(torch.argmin(final_bias_grad).item())


def gradient_mse(dummy_grads: tuple[torch.Tensor, ...], target_grads: list[torch.Tensor]) -> torch.Tensor:
    loss = dummy_grads[0].new_tensor(0.0)
    for dummy, target in zip(dummy_grads, target_grads):
        loss = loss + F.mse_loss(dummy, target, reduction="sum")
    return loss


def main() -> None:
    args = parse_args()
    if args.threads > 0:
        torch.set_num_threads(args.threads)

    dist_dir = args.dist_dir.resolve()
    model = load_public_model(dist_dir)
    set_seeds(args.seed)
    payload = torch.load(dist_dir / "gradients.pt", map_location="cpu", weights_only=True)
    target_grads = [grad.detach().to(dtype=torch.float32) for grad in payload["grads"]]
    input_shape = tuple(args.input_shape)
    label = infer_label_from_bias_grad(target_grads)
    y = torch.tensor([label], dtype=torch.long)

    out_dir = args.out_dir
    if out_dir is None:
        out_dir = Path.cwd() / "reconstructions" / f"seed_{args.seed}"
    out_dir.mkdir(parents=True, exist_ok=True)

    image_logits = torch.randn(input_shape, dtype=torch.float32) * 0.25
    image_logits.requires_grad_(True)
    optimizer = torch.optim.Adam([image_logits], lr=args.lr)

    parameters = tuple(model.parameters())
    for step in range(args.steps + 1):
        if step in {args.steps // 2, (3 * args.steps) // 4}:
            for group in optimizer.param_groups:
                group["lr"] *= 0.5

        optimizer.zero_grad(set_to_none=True)
        candidate = torch.sigmoid(image_logits)
        loss = F.cross_entropy(model(candidate), y)
        dummy_grads = torch.autograd.grad(loss, parameters, create_graph=True)
        match_loss = gradient_mse(dummy_grads, target_grads)
        tv_loss = total_variation(candidate)
        objective = match_loss + args.tv_weight * tv_loss
        objective.backward()
        optimizer.step()

        if step % args.progress_every == 0 or step == args.steps:
            save_image(candidate, out_dir / f"progress_{step:05d}.png")
            print(
                f"step={step:05d} label={label} "
                f"grad_mse={match_loss.item():.6e} tv={tv_loss.item():.6e}"
            )

    final_image = torch.sigmoid(image_logits)
    save_image(final_image, out_dir / "final_reconstruction.png")
    print(f"saved {out_dir / 'final_reconstruction.png'}")


if __name__ == "__main__":
    main()
