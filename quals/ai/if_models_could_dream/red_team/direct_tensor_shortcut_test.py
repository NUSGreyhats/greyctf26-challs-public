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


FORBIDDEN_KEYS = {
    "entry_projection",
    "transition",
    "horizon",
    "readout",
    "bias",
    "decoder_bit_accuracy",
    "entry_mse",
    "transition_mse",
}


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


def ascii_from_logits(logits: torch.Tensor) -> str:
    chars = []
    for row in logits.detach().cpu().float():
        value = 0
        for bit in (row > 0).tolist():
            value = (value << 1) | int(bit)
        if 32 <= value <= 126:
            chars.append(chr(value))
        else:
            return ""
    return "".join(chars)


def matches_digest(candidate: str, expected: str) -> bool:
    for end in range(1, len(candidate) + 1):
        if hashlib.sha256(candidate[:end].encode()).hexdigest() == expected:
            return True
    return False


def try_linear_recurrence(tensors: dict[str, torch.Tensor]) -> list[str]:
    matrices = [(name, value.detach().cpu().float()) for name, value in tensors.items() if value.ndim == 2]
    starts = []
    for name, value in tensors.items():
        arr = value.detach().cpu().float()
        if arr.ndim == 1:
            starts.append((name, arr))
        elif arr.ndim == 2 and arr.shape[0] <= 8:
            starts.extend((f"{name}[{idx}]", row) for idx, row in enumerate(arr))
    guesses = []
    for readout_name, readout in matrices:
        if 8 not in readout.shape:
            continue
        readout = readout if readout.shape[1] == 8 else readout.T
        latent_dim = readout.shape[0]
        transitions = [(name, matrix) for name, matrix in matrices if matrix.shape == (latent_dim, latent_dim)]
        biases = [torch.zeros(8)]
        biases.extend(value.detach().cpu().float() for value in tensors.values() if value.ndim == 1 and value.numel() == 8)
        candidate_starts = [(name, start) for name, start in starts if start.numel() == latent_dim]
        for transition_name, transition in transitions:
            for start_name, start in candidate_starts:
                for scale in (-100.0, -10.0, -1.0, 1.0, 10.0, 100.0):
                    for transpose in (False, True):
                        for bias in biases:
                            latent = start * scale
                            rows = []
                            for _ in range(128):
                                rows.append(latent @ readout + bias)
                                latent = (transition.T if transpose else transition) @ latent
                            guess = ascii_from_logits(torch.stack(rows))
                            if guess:
                                guesses.append(guess)
    return guesses


def walk(value, tensors: dict[str, torch.Tensor], prefix: str = ""):
    if isinstance(value, torch.Tensor):
        tensors[prefix or "tensor"] = value
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in FORBIDDEN_KEYS:
                raise SystemExit(f"direct byte-model key exported: {key}")
            if any(marker in lowered for marker in ("flag", "lamp", "panel", "start_state", "state_bank")):
                raise SystemExit(f"overly direct tensor key: {key}")
            yield from walk(item, tensors, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            yield from walk(item, tensors, f"{prefix}.{idx}" if prefix else str(idx))


def main() -> int:
    expected = digest()
    all_tensors: dict[str, torch.Tensor] = {}
    for path in (DIST / "model").glob("*.pt"):
        artifact = torch.load(path, map_location="cpu", weights_only=False)
        tensors: dict[str, torch.Tensor] = {}
        if path.name == "decoder.pt" and isinstance(artifact, dict):
            state = artifact.get("state_dict")
            if not isinstance(state, dict):
                raise SystemExit("decoder checkpoint is not a neural state_dict")
            if any(value.ndim == 2 and 8 in value.shape for value in state.values() if isinstance(value, torch.Tensor)):
                raise SystemExit("decoder checkpoint contains byte-width linear output")
        for tensor in walk(artifact, tensors):
            for guess in try_rows_as_ascii(tensor):
                if matches_digest(guess, expected):
                    raise SystemExit(f"direct tensor rows decode verifier payload: {path}")
        for guess in try_linear_recurrence(tensors):
            if matches_digest(guess, expected):
                raise SystemExit(f"linear recurrence decodes verifier payload: {path}")
        for name, tensor in tensors.items():
            all_tensors[f"{path.name}:{name}"] = tensor
    for guess in try_linear_recurrence(all_tensors):
        if matches_digest(guess, expected):
            raise SystemExit("linear recurrence decodes verifier payload across checkpoint files")
    print("direct tensor shortcut: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
