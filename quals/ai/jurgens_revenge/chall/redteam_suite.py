from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import warnings
from pathlib import Path

sys.dont_write_bytecode = True

warnings.filterwarnings("ignore", message="Failed to initialize NumPy*", category=UserWarning)
import torch

from common import DEFAULT_PAYLOAD, PAYLOAD_LEN, PUBLIC_FILES, PUBLIC_KEYS, payload_to_flag


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Red-team the jurgens_revenge bundle.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--fast", action="store_true")
    group.add_argument("--deep", action="store_true")
    parser.add_argument("--expected-payload")
    return parser.parse_args()


def run_py(args: list[str], cwd: Path) -> tuple[int, str, str, int]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    start = time.perf_counter_ns()
    proc = subprocess.run(args, cwd=str(cwd), text=True, capture_output=True, check=False, env=env)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip(), time.perf_counter_ns() - start


def run_checker(flag: str) -> tuple[int, str, str, int]:
    return run_py([sys.executable, str(DIST_DIR / "check.py"), flag], DIST_DIR)


def artifact_scan(expected_payload: str | None) -> list[str]:
    failures: list[str] = []
    tokens = [
        b"metadata.json",
        b"expected_payload",
        b"char_masks",
        b"pair_tables",
        b"triple_tables",
        b"target_residue",
        b"alias_indices",
        b"jurgens_palace",
    ]
    if expected_payload:
        tokens.extend([expected_payload.encode(), payload_to_flag(expected_payload).encode()])
    paths = [p for p in DIST_DIR.rglob("*") if p.is_file()]
    for path in paths:
        data = path.read_bytes()
        for token in tokens:
            if token in data:
                failures.append(f"{path} contains forbidden token {token!r}")
    return failures


def checkpoint_surface() -> list[str]:
    raw = torch.load(DIST_DIR / "model.pt", map_location="cpu")
    failures: list[str] = []
    if set(raw) != PUBLIC_KEYS:
        failures.append(f"unexpected checkpoint keys: {sorted(raw)}")
    banned_keys = {
        "char_masks",
        "pair_tables",
        "triple_tables",
        "target_residues",
        "lstm.input_gate_lut.weight",
        "cell.write.weight",
        "cell.unpack.weight",
        "hidden.project.weight",
        "readout.project.weight",
        "gate.update.weight",
        "gate.update.bias",
        "memory.recurrent.weight",
        "memory.bias",
        "norm.scale",
    }
    if set(raw) & banned_keys:
        failures.append("checkpoint exposes removed semantic or redundant keys")
    text_keys = " ".join(raw.keys())
    for token in ("phase", "prev", "status", "payload", "memory", "teacher", "wire"):
        if token in text_keys:
            failures.append(f"checkpoint key surface contains semantic token {token!r}")
    if any(key.endswith(suffix) for key in raw for suffix in (".i", ".v", ".s")):
        failures.append("checkpoint still uses sparse index/value/shape archive keys")
    int_keys = [key for key, value in raw.items() if not value.is_floating_point() and key != "config.meta"]
    if int_keys:
        failures.append(f"checkpoint exposes non-config integer tensors: {int_keys}")
    if raw["config.meta"].numel() != 13 or raw["core.input.weight"].ndim != 3 or raw["core.context.weight"].ndim != 3:
        failures.append("checkpoint does not look like a normal recurrent state_dict")
    return failures


def checker_surface(expected_payload: str | None) -> list[str]:
    if expected_payload is None:
        return []
    cases = [
        (payload_to_flag(expected_payload), True),
        (payload_to_flag(expected_payload[:-1] + ("a" if expected_payload[-1] != "a" else "b")), False),
        (payload_to_flag("a" * PAYLOAD_LEN), False),
        (f"grey{{{expected_payload[:-1]}}}", False),
        (f"grey{{{expected_payload}a}}", False),
    ]
    failures: list[str] = []
    for flag, should_accept in cases:
        rc, stdout, stderr, _ = run_checker(flag)
        accepted = rc == 0 and stdout == "accepted" and stderr == ""
        rejected = rc != 0 and stdout == "rejected" and stderr == ""
        if should_accept and not accepted:
            failures.append(f"checker rejected expected flag: {stdout!r} {stderr!r}")
        if not should_accept and not rejected:
            failures.append(f"checker leaked non-binary or accepted wrong flag: {flag!r} -> {rc} {stdout!r} {stderr!r}")
    return failures


def black_box_probe(expected_payload: str | None) -> list[str]:
    probes = [
        payload_to_flag("a" * PAYLOAD_LEN),
        payload_to_flag((DEFAULT_PAYLOAD[::-1])[:PAYLOAD_LEN]),
        payload_to_flag(("abcdefghijklmnopqrstuvwxyz0123456789_" * 2)[:PAYLOAD_LEN]),
    ]
    if expected_payload:
        probes.append(payload_to_flag(expected_payload[:-1] + ("a" if expected_payload[-1] != "a" else "b")))
    outputs = [run_checker(flag) for flag in probes]
    failures = []
    if any(stderr for _, _, stderr, _ in outputs):
        failures.append("checker wrote stderr during black-box probes")
    if any(stdout not in {"accepted", "rejected"} for _, stdout, _, _ in outputs):
        failures.append("checker exposed non-binary output")
    timings = [elapsed for _, _, _, elapsed in outputs]
    if timings and max(timings) > max(250_000_000, min(timings) * 20):
        failures.append(f"checker timing spread too large: {timings}")
    return failures


def old_symbolic_solver_fails() -> list[str]:
    raw = torch.load(DIST_DIR / "model.pt", map_location="cpu")
    old_keys = {
        "lstm.input_gate_lut.weight",
        "lstm.recurrent_gate_lut.weight",
        "lstm.context_gate_lut.weight",
        "char_masks",
        "pair_tables",
        "triple_tables",
        "gate.recurrent.weight",
        "hidden.project.weight",
        "output.probe.weight",
        "b.i",
        "b.v",
        "b.s",
        "u",
        "v",
    }
    if set(raw) & old_keys:
        return ["old symbolic or semantic checkpoint keys are present"]
    return []


def sparse_output_shortcut_guard() -> list[str]:
    sys.path.insert(0, str(DIST_DIR))
    try:
        from model import RevengeModel

        model = RevengeModel.from_paths(DIST_DIR / "model.pt", DIST_DIR / "alphabet.json")
    finally:
        if sys.path and sys.path[0] == str(DIST_DIR):
            sys.path.pop(0)
    binary_dim = model.binary_dim
    packed_dim = model.packed_dim
    readout_dim = model.readout_dim
    probe_w = model.classifier.features.weight.to(dtype=torch.float64)
    head_w = model.classifier.output.weight[0].to(dtype=torch.float64)
    selected_rows = [idx for idx, value in enumerate(head_w.tolist()) if abs(value) > 1e-9]
    failures: list[str] = []
    for row in selected_rows:
        terminal = probe_w[row, readout_dim : readout_dim + packed_dim]
        nonzero = terminal.abs().gt(1e-9).nonzero().flatten().tolist()
        if len(nonzero) != 1:
            continue
        col = nonzero[0]
        kind = "binary" if col < binary_dim else "memory"
        failures.append(f"selected evidence row {row} exposes one-sparse terminal {kind} predicate")
    if len(selected_rows) <= 12:
        failures.append("output head exposes only the exact acceptance predicate rows")
    return failures


def solver_report(expected_payload: str | None) -> list[str]:
    rc, stdout, stderr, _ = run_py([sys.executable, str(ROOT / "solve" / "solve.py"), "--report"], ROOT)
    if rc != 0:
        return [stdout or stderr or "solve.py --report failed"]
    failures: list[str] = []
    if expected_payload and payload_to_flag(expected_payload) not in stdout:
        failures.append("solver did not recover expected flag")
    for token in ("Recovered mechanism:", "causal patching", "Z3 uniqueness: proved", "decoy circuits"):
        if token not in stdout:
            failures.append(f"solver report missing {token!r}")
    return failures


def compact_artifact_guard() -> list[str]:
    failures: list[str] = []
    size = (DIST_DIR / "model.pt").stat().st_size
    if size > 2_000_000:
        failures.append(f"public model.pt too large: {size} bytes")
    model_text = (DIST_DIR / "model.py").read_text(encoding="utf-8")
    for token in ("trace_indices", "trace_payload", "terminal_from_cell", "advance_cell"):
        if token in model_text:
            failures.append(f"public runtime still exposes debug helper {token!r}")
    rc, stdout, stderr, _ = run_py(
        [sys.executable, "-c", "from pathlib import Path; from model import RevengeModel; print(RevengeModel.from_paths(Path('model.pt'), Path('alphabet.json')))"],
        DIST_DIR,
    )
    if rc != 0:
        failures.append(stdout or stderr or "could not print public model")
    for token in ("Embedding", "RecurrentCore", "StepProject", "Linear", "VerifierHead"):
        if token not in stdout:
            failures.append(f"model repr missing normal module token {token!r}")
    return failures


def run_suite(args: argparse.Namespace) -> list[str]:
    expected_payload = args.expected_payload
    failures: list[str] = []
    failures.extend(artifact_scan(expected_payload))
    failures.extend(checkpoint_surface())
    failures.extend(checker_surface(expected_payload))
    failures.extend(black_box_probe(expected_payload))
    failures.extend(old_symbolic_solver_fails())
    failures.extend(compact_artifact_guard())
    failures.extend(sparse_output_shortcut_guard())
    if args.deep:
        failures.extend(solver_report(expected_payload))
    return failures


def main() -> int:
    args = parse_args()
    failures = run_suite(args)
    if failures:
        print("red-team suite failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("red-team suite passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
