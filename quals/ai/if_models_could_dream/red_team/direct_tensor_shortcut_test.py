#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def digest() -> str:
    return re.search(r'EXPECTED_SHA256 = "([0-9a-f]{64})"', (DIST / "verify.py").read_text()).group(1)


def try_rows_as_ascii(tensor: torch.Tensor) -> list[str]:
    arr = tensor.detach().cpu().float()
    guesses: list[str] = []
    if arr.ndim == 2 and arr.shape[1] == 8:
        for threshold in (0.0, 0.25, 0.5, arr.mean().item()):
            chars = []
            for row in arr:
                value = 0
                for bit in (row > threshold).tolist():
                    value = (value << 1) | int(bit)
                if 32 <= value <= 126:
                    chars.append(chr(value))
            guesses.append("".join(chars))
    return guesses


def walk(value):
    if isinstance(value, torch.Tensor):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in ("flag", "lamp", "panel", "start_state", "state_bank")):
                raise SystemExit(f"overly direct tensor key: {key}")
            yield from walk(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from walk(item)


def main() -> int:
    expected = digest()
    for path in (DIST / "model").glob("*.pt"):
        artifact = torch.load(path, map_location="cpu", weights_only=False)
        for tensor in walk(artifact):
            for guess in try_rows_as_ascii(tensor):
                if hashlib.sha256(guess.encode()).hexdigest() == expected:
                    raise SystemExit(f"direct tensor rows decode verifier payload: {path}")
    print("direct tensor shortcut: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
