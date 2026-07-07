from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "dist"
PRIVATE_DIR = ROOT / "chall"
FLAG_PATH = PRIVATE_DIR / "flag.txt"
ORIGINAL_PATH = PRIVATE_DIR / "original_sample.png"
GRADIENTS_PATH = PUBLIC_DIR / "gradients.pt"
WEIGHTS_PATH = PUBLIC_DIR / "model_weights.pt"

GENERATION_SEED = 52421906
TRUE_LABEL = 7
INPUT_SHAPE = [1, 1, 64, 64]
NUM_CLASSES = 10

# Organizer check:
#   pyenv activate cs5242
#   for s in $(seq 0 10); do python solve/solution.py --seed "$s"; done
# All eleven final outputs should visibly reveal the flag.

# VIBECODED: Glyph pixel-drawing system to render the flag as an image.
GLYPHS: dict[str, tuple[str, ...]] = {
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    "a": ("00000", "01110", "00001", "01111", "10001", "10011", "01101"),
    "d": ("00001", "00001", "01101", "10011", "10001", "10011", "01101"),
    "e": ("00000", "01110", "10001", "11111", "10000", "10001", "01110"),
    "g": ("00000", "01101", "10011", "10001", "01111", "00001", "01110"),
    "i": ("00100", "00000", "01100", "00100", "00100", "00100", "01110"),
    "n": ("00000", "10110", "11001", "10001", "10001", "10001", "10001"),
    "r": ("00000", "10110", "11001", "10000", "10000", "10000", "10000"),
    "y": ("00000", "10001", "10001", "01111", "00001", "10001", "01110"),
    "z": ("00000", "11111", "00010", "00100", "01000", "10000", "11111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "_": ("00000", "00000", "00000", "00000", "00000", "00000", "11111"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    "{": ("00011", "00100", "00100", "11000", "00100", "00100", "00011"),
    "}": ("11000", "00100", "00100", "00011", "00100", "00100", "11000"),
}


def set_seeds(seed: int) -> None:
    '''
    Fix RNGs (mostly to check the chall actually works with most fixed seeds).
    '''
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def draw_pixel_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, value: int) -> None:
    '''
    VIBECODED: Something about drawing pixel texts.
    '''
    x0, y0 = xy
    cursor_x = x0
    for char in text:
        glyph = GLYPHS[char]
        for row, bits in enumerate(glyph):
            for col, bit in enumerate(bits):
                if bit == "1":
                    draw.point((cursor_x + col, y0 + row), fill=value)
        cursor_x += 6


def render_stamp(flag: str) -> Image.Image:
    '''
    VIBECODED: Stitch all the pixels together into a funny image.
    '''
    image = Image.new("L", (64, 64), 238)
    draw = ImageDraw.Draw(image)

    draw.rectangle((1, 1, 62, 62), outline=42)
    draw.rectangle((3, 3, 60, 60), outline=170)
    draw.line((8, 5, 55, 5), fill=128)
    draw.line((8, 58, 55, 58), fill=128)
    draw.line((5, 8, 5, 55), fill=128)
    draw.line((58, 8, 58, 55), fill=128)
    draw.rectangle((47, 48, 57, 57), outline=92)
    draw.line((49, 52, 52, 55), fill=92)
    draw.line((52, 55, 56, 49), fill=92)

    lines = [
        flag[0:9],
        flag[9:19],
        flag[19:29],
        flag[29:39],
        flag[39:49],
        flag[49:],
    ]
    y = 8
    for line in lines:
        draw_pixel_text(draw, (3, y), line, 24)
        y += 8

    return image


def degrade_image(image: Image.Image) -> Image.Image:
    '''
    VIBECODED: TBH IDK why Codex felt the need to do this shit
    '''
    rng = np.random.default_rng(GENERATION_SEED)
    image = image.rotate(0.55, resample=Image.Resampling.BICUBIC, fillcolor=238)
    image = image.transform(
        (64, 64),
        Image.Transform.AFFINE,
        (1.0, 0.010, -0.35, -0.006, 1.0, 0.25),
        resample=Image.Resampling.BICUBIC,
        fillcolor=238,
    )
    image = image.filter(ImageFilter.GaussianBlur(radius=0.28))
    arr = np.asarray(image, dtype=np.float32)
    arr += rng.normal(loc=0.0, scale=2.0, size=arr.shape).astype(np.float32)
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="L")


def init_weights(module: torch.nn.Module) -> None:
    '''
    Initialize the weights of the model.
    '''
    if isinstance(module, torch.nn.Conv2d):
        torch.nn.init.normal_(module.weight, mean=0.0, std=0.035)
        torch.nn.init.constant_(module.bias, 0.18)
    elif isinstance(module, torch.nn.Linear):
        torch.nn.init.normal_(module.weight, mean=0.0, std=0.015)
        torch.nn.init.zeros_(module.bias)


def create_model():
    '''
    Create challenge model.
    '''
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(PUBLIC_DIR))
    from model import build_model

    model = build_model()
    model.apply(init_weights)
    model.eval()
    return model


def image_to_tensor(image: Image.Image) -> torch.Tensor:
    arr = np.asarray(image, dtype=np.float32) / 255.0
    return torch.from_numpy(arr).view(1, 1, 64, 64)


def main() -> None:
    set_seeds(GENERATION_SEED)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)

    flag = FLAG_PATH.read_text(encoding="utf-8").strip()
    sample = degrade_image(render_stamp(flag))
    sample.save(ORIGINAL_PATH)

    model = create_model()
    torch.save(model.state_dict(), WEIGHTS_PATH)

    x = image_to_tensor(sample)
    y = torch.tensor([TRUE_LABEL], dtype=torch.long)

    model.zero_grad(set_to_none=True)
    loss = F.cross_entropy(model(x), y)
    loss.backward()
    grads = [parameter.grad.detach().clone().to(torch.float32) for parameter in model.parameters()]

    torch.save(
        {
            "grads": grads,
            "input_shape": INPUT_SHAPE,
            "loss": "cross_entropy",
            "num_classes": NUM_CLASSES,
            "dtype": "float32",
        },
        GRADIENTS_PATH,
    )

    print(f"wrote {GRADIENTS_PATH.relative_to(ROOT)}")
    print(f"wrote {WEIGHTS_PATH.relative_to(ROOT)}")
    print(f"wrote {ORIGINAL_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
